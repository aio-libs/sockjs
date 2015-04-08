import asyncio
import random
import logging
import hashlib
from aiohttp import web, hdrs

from sockjs.session import SessionManager
from sockjs.protocol import IFRAME_HTML, json
from sockjs.transports import handlers
from sockjs.transports.utils import session_cookie
from sockjs.transports.utils import cors_headers
from sockjs.transports.utils import cache_headers
from sockjs.transports.rawwebsocket import RawWebSocketTransport

log = logging.getLogger('sockjs')


def get_manager(name, app):
    return app['__sockjs_managers__'][name]


def add_endpoint(app, handler, *, name='', prefix='/sockjs',
                 manager=None, disable_transports=(),
                 sockjs_cdn='http://cdn.sockjs.org/sockjs-0.3.4.min.js',
                 cookie_needed=True):

    router = app.router

    # set session manager
    if manager is None:
        manager = SessionManager(name, app, handler)

    if manager.name != name:
        raise ValueError(
            "Session manage must have same name as sockjs route")

    managers = app.setdefault('__sockjs_managers__', {})
    if name in managers:
        raise ValueError("SockJS '%s' route already registered" % name)

    managers[name] = manager

    # register routes
    route = SockJSRoute(
        name, manager, sockjs_cdn, disable_transports, cookie_needed)

    if prefix.endswith('/'):
        prefix = prefix[:-1]

    route_name = 'sockjs-url-%s-greeting' % name
    router.add_route(hdrs.METH_GET, prefix, route.greeting)

    route_name = 'sockjs-url-%s' % name
    router.add_route(hdrs.METH_GET, '%s/' % prefix, route.greeting)

    route_name = 'sockjs-%s' % name
    router.add_route(
        hdrs.METH_ANY,
        '%s/{server}/{session}/{transport}' % prefix, route.handler)

    route_name = 'sockjs-websocket-%s' % name
    router.add_route(
        hdrs.METH_GET, '%s/websocket' % prefix, route.websocket)

    route_name = 'sockjs-info-%s' % name
    router.add_route(
        hdrs.METH_GET, '%s/info' % prefix, route.info)
    router.add_route(
        hdrs.METH_OPTIONS, '%s/info' % prefix, route.info_options)

    route_name = 'sockjs-iframe-%s' % name
    router.add_route(
        hdrs.METH_GET, '%s/iframe.html' % prefix, route.iframe)

    route_name = 'sockjs-iframe-ver-%s' % name
    router.add_route(
        hdrs.METH_GET, '%s/iframe{version}.html' % prefix, route.iframe)

    # start session gc
    # cfg.action('sockjs:gc:%s'%name,
    #           session_manager.start, order=999999+1)


class SockJSRoute:

    def __init__(self, name, manager,
                 sockjs_cdn, disable_transports, cookie_needed=True):
        self.name = name
        self.manager = manager
        self.disable_transports = dict((k, 1) for k in disable_transports)
        self.cookie_needed = cookie_needed
        self.iframe_html = (IFRAME_HTML % sockjs_cdn).encode('utf-8')
        self.iframe_html_hxd = hashlib.md5(self.iframe_html).hexdigest()

    def handler(self, request):
        info = request.match_info

        # lookup transport
        tid = info['transport']

        if tid not in handlers or tid in self.disable_transports:
            return web.HTTPNotFound()

        create, transport = handlers[tid]

        # session
        manager = self.manager
        if not manager.started:
            manager.start()

        sid = info['session']
        if not sid or '.' in sid or '.' in info['server']:
            return web.HTTPNotFound()

        try:
            session = manager.get(sid, create, request=request)
        except KeyError:
            return web.HTTPNotFound(headers=session_cookie(request))

        t = transport(manager, session, request)
        try:
            return (yield from t.process())
        except asyncio.CancelledError:
            raise
        except web.HTTPException as exc:
            return exc
        except Exception as exc:
            log.exception('Exception in transport: %s' % tid)
            return web.HTTPInternalServerError()

    def websocket(self, request):
        # session
        manager = self.manager

        sid = '%0.9d' % random.randint(1, 2147483647)

        session = manager.get(sid, True, request=request)

        # websocket
        if hdrs.ORIGIN in request.headers:
            return web.HTTPNotFound()

        transport = RawWebSocketTransport(manager, session, request)
        try:
            return (yield from transport.process())
        except asyncio.CancelledError:
            raise
        except web.HTTPException as exc:
            return exc
        except Exception as exc:
            log.exception('Exception in transport: %s' % tid)
            return web.HTTPInternalServerError()

    def info(self, request):
        resp = web.Response(
            content_type='application/json; charset=UTF-8')
        resp.headers[hdrs.CACHE_CONTROL] = (
            'no-store, no-cache, must-revalidate, max-age=0')
        resp.headers.extend(cors_headers(request))

        info = {'entropy': random.randint(1, 2147483647),
                'websocket': 'websocket' not in self.disable_transports,
                'cookie_needed': self.cookie_needed,
                'origins': ['*:*']}
        resp.text = json.dumps(info)
        return resp

    def info_options(self, request):
        resp = web.Response(
            status=204, content_type='application/json; charset=UTF-8')
        resp.headers[hdrs.CACHE_CONTROL] = (
            'no-store, no-cache, must-revalidate, max-age=0')
        resp.headers[hdrs.ACCESS_CONTROL_ALLOW_METHODS] = "OPTIONS, GET"
        resp.headers.extend(cors_headers(request.headers))
        resp.headers.extend(cache_headers())
        resp.headers.extend(session_cookie(request))
        return resp

    def iframe(self, request):
        cached = request.headers.get(hdrs.IF_NONE_MATCH)
        if cached:
            response = web.Response(status=304)
            response.headers.extend(cache_headers())
            return response

        return web.Response(
            body=self.iframe_html,
            content_type='text/html; charset=UTF-8',
            headers=((hdrs.ETAG, self.iframe_html_hxd),) + cache_headers())

    def greeting(self, request):
        return web.Response(body=b'Welcome to SockJS!\n',
                            content_type='text/plain; charset=UTF-8')
