import logging
import hashlib
from datetime import datetime, timedelta
from pyramid.response import Response
from pyramid.exceptions import ConfigurationError
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest

from pyramid_sockjs.protocol import close_frame
from pyramid_sockjs.session import Session
from pyramid_sockjs.session import SessionManager
from pyramid_sockjs.protocol import IFRAME_HTML
from pyramid_sockjs.transports import handlers
from pyramid_sockjs.transports import session_cookie
from pyramid_sockjs.websocket import HandshakeError
from pyramid_sockjs.websocket import init_websocket

log = logging.getLogger('pyramid_sockjs')



def add_sockjs_route(cfg, name='', prefix='/__sockjs__',
                     session=Session, session_manager=None,
                     sockjs_cdn='http://cdn.sockjs.org/sockjs-0.2.0.min.js'):
    # set session manager
    if session_manager is None:
        session_manager = SessionManager(name, cfg.registry, session=session)

    if session_manager.name != name:
        raise ConfigurationError(
            "Session manage has to have same name as sockjs route")

    if not hasattr(cfg.registry, '__sockjs_managers__'):
        cfg.registry.__sockjs_managers__ = {}

    if name in cfg.registry.__sockjs_managers__:
        raise ConfigurationError("SockJS '%s' route already registered"%name)

    cfg.registry.__sockjs_managers__[name] = session_manager

    # start gc
    session_manager.start()

    # register routes
    sockjs = SockJSRoute(name, session_manager, sockjs_cdn)

    if prefix.endswith('/'):
        prefix = prefix[:-1]

    route_name = 'sockjs-url-%s-greeting'%name
    cfg.add_route(route_name, prefix)
    cfg.add_view(route_name=route_name, view=sockjs.greeting)

    route_name = 'sockjs-url-%s'%name
    cfg.add_route(route_name, '%s/'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.greeting)

    route_name = 'sockjs-%s'%name
    cfg.add_route(route_name, '%s/{server}/{session}/{transport}'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.handler)

    route_name = 'sockjs-info-%s'%name
    cfg.add_route(route_name, '%s/info'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.info)

    route_name = 'sockjs-iframe-%s'%name
    cfg.add_route(route_name, '%s/iframe.html'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.iframe)

    route_name = 'sockjs-iframe-ver-%s'%name
    cfg.add_route(route_name, '%s/iframe{version}.html'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.iframe)


class SockJSRoute(object):

    def __init__(self, name, session_manager, sockjs_cdn):
        self.name = name
        self.session_manager = session_manager
        self.iframe_html = IFRAME_HTML%sockjs_cdn
        self.iframe_html_hxd = hashlib.md5(self.iframe_html).hexdigest()

    def handler(self, request):
        matchdict = request.matchdict

        # lookup transport
        tid = matchdict['transport']

        if tid not in handlers:
            return HTTPNotFound()

        create, transport = handlers[tid]

        # session
        manager = self.session_manager

        sid = matchdict['session']
        if '.' in sid:
            return HTTPNotFound()

        if manager.is_acquired(sid):
            request.response.body = close_frame(
                2010, "Another connection still open")
            return request.response

        try:
            session = manager.acquire(sid, create, request)
        except KeyError:
            return HTTPNotFound(headers=(session_cookie(request),))

        request.environ['wsgi.sockjs_session'] = session

        # websocket
        if tid == 'websocket':
            try:
                res = init_websocket(request)
                if res is not None:
                    manager.release(session)
                    return res
            except Exception as exc:
                manager.release(session)
                if isinstance(exc, Response):
                    return exc
                return HTTPBadRequest(str(exc))

        try:
            return transport(session, request)
        except Exception as exc:
            manager.release(session)
            log.exception('Exception in transport: %s'%tid)
            return HTTPBadRequest(str(exc))

    def info(self, request):
        request.response.body = \
            str(map(str, self.session_manager.sessions.values()))
        return request.response

    td365 = timedelta(days=365)
    td365seconds = int(td365.total_seconds())

    def iframe(self, request):
        response = request.response

        d = datetime.now() + self.td365
        
        response.headers = [
            ('Access-Control-Max-Age', self.td365seconds),
            ('Cache-Control', 'max-age=%d, public' % self.td365seconds),
            ('Expires', d.strftime('%a, %d %b %Y %H:%M:%S')),
            ]

        cached = request.environ.get('HTTP_IF_NONE_MATCH')
        if cached:
            response.status = 304
            return response

        response.headers['Content-Type'] = 'text/html; charset=UTF-8'
        response.headers['ETag'] = self.iframe_html_hxd
        response.body = self.iframe_html
        return response

    def greeting(self, request):
        request.response.content_type = 'text/plain; charset=UTF-8'
        request.response.body = 'Welcome to SockJS!\n'
        return request.response


class GetSessionManager(object):
    """ Pyramid's request.get_sockjs_manager implementation """

    def __init__(self, registry):
        self.registry = registry

    def __call__(self, name=''):
        try:
            return self.registry.__sockjs_managers__[name]
        except AttributeError:
            raise KeyError(name)
