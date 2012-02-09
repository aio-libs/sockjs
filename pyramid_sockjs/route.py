import random
import logging
import hashlib
from datetime import datetime, timedelta
from pyramid.response import Response
from pyramid.exceptions import ConfigurationError
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest

from pyramid_sockjs.session import SessionManager
from pyramid_sockjs.protocol import json
from pyramid_sockjs.protocol import IFRAME_HTML
from pyramid_sockjs.websocket import init_websocket
from pyramid_sockjs.transports import handlers
from pyramid_sockjs.transports.utils import session_cookie
from pyramid_sockjs.transports.utils import cors_headers
from pyramid_sockjs.transports.utils import cache_headers
from pyramid_sockjs.transports.websocket import RawWebSocketTransport

log = logging.getLogger('pyramid_sockjs')


def add_sockjs_route(cfg, name='', prefix='/__sockjs__',
                     session=None, session_manager=None,
                     disable_transports=(),
                     sockjs_cdn='http://cdn.sockjs.org/sockjs-0.2.0.min.js',
                     permission=None, decorator=None):
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
    sockjs = SockJSRoute(name, session_manager, sockjs_cdn, disable_transports)

    if prefix.endswith('/'):
        prefix = prefix[:-1]

    route_name = 'sockjs-url-%s-greeting'%name
    cfg.add_route(route_name, prefix)
    cfg.add_view(route_name=route_name, view=sockjs.greeting,
                 permission=permission, decorator=decorator)

    route_name = 'sockjs-url-%s'%name
    cfg.add_route(route_name, '%s/'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.greeting,
                 permission=permission, decorator=decorator)

    route_name = 'sockjs-%s'%name
    cfg.add_route(route_name, '%s/{server}/{session}/{transport}'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.handler,
                 permission=permission, decorator=decorator)

    route_name = 'sockjs-websocket-%s'%name
    cfg.add_route(route_name, '%s/websocket'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.websocket,
                 permission=permission, decorator=decorator)

    route_name = 'sockjs-info-%s'%name
    cfg.add_route(route_name, '%s/info'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.info,
                 permission=permission, decorator=decorator)

    route_name = 'sockjs-iframe-%s'%name
    cfg.add_route(route_name, '%s/iframe.html'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.iframe,
                 permission=permission, decorator=decorator)

    route_name = 'sockjs-iframe-ver-%s'%name
    cfg.add_route(route_name, '%s/iframe{version}.html'%prefix)
    cfg.add_view(route_name=route_name, view=sockjs.iframe,
                 permission=permission, decorator=decorator)


class SockJSRoute(object):

    def __init__(self, name, session_manager, sockjs_cdn, disable_transports):
        self.name = name
        self.session_manager = session_manager
        self.disable_transports = dict((k,1) for k in disable_transports)
        self.iframe_html = IFRAME_HTML%sockjs_cdn
        self.iframe_html_hxd = hashlib.md5(self.iframe_html).hexdigest()

    def handler(self, request):
        matchdict = request.matchdict

        # lookup transport
        tid = matchdict['transport']

        if tid not in handlers or tid in self.disable_transports:
            return HTTPNotFound()

        create, transport = handlers[tid]

        # session
        manager = self.session_manager

        sid = matchdict['session']
        if not sid or '.' in sid or '.' in matchdict['server']:
            return HTTPNotFound()

        try:
            session = manager.get(sid, create)
        except KeyError:
            return HTTPNotFound(headers=(session_cookie(request),))

        request.environ['wsgi.sockjs_session'] = session

        # websocket
        if tid == 'websocket':
            if 'HTTP_SEC_WEBSOCKET_VERSION' not in request.environ and \
                   'HTTP_ORIGIN' in request.environ:
                return HTTPNotFound()

            res = init_websocket(request)
            if res is not None:
                return res

        try:
            return transport(session, request)
        except Exception as exc:
            session.release()
            log.exception('Exception in transport: %s'%tid)
            return HTTPBadRequest(str(exc))

    def websocket(self, request):
        # session
        manager = self.session_manager

        sid = '%0.9d'%random.randint(1, 2147483647)
        session = manager.get(sid, True)
        request.environ['wsgi.sockjs_session'] = session

        # websocket
        if 'HTTP_ORIGIN' in request.environ:
            return HTTPNotFound()

        res = init_websocket(request)
        if res is not None:
            return res

        return RawWebSocketTransport(session, request)

    def info(self, request):
        response = request.response
        response.content_type = 'application/json; charset=UTF-8'
        response.headerlist.append(
            ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0'))
        response.headerlist.extend(cors_headers(request))

        if request.method == 'OPTIONS':
            session_cookie(request)
            response.status = 204
            response.headerlist.append(
                ("Access-Control-Allow-Methods", "OPTIONS, GET"))
            response.headerlist.extend(cache_headers(request))
            return response

        info = {'entropy': random.randint(1, 2147483647),
                'websocket': 'websocket' not in self.disable_transports,
                'cookie_needed': True,
                'origins': ['*:*']}
        response.body = json.dumps(info)
        return response

    def iframe(self, request):
        response = request.response
        response.headerlist.extend(cache_headers(request))

        cached = request.environ.get('HTTP_IF_NONE_MATCH')
        if cached:
            response.status = 304
            del response.headers['Content-Type']
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


def get_session_manager(name, registry):
    try:
        return registry.__sockjs_managers__[name]
    except AttributeError:
        raise KeyError(name)
