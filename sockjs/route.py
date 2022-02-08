import asyncio
import hashlib
import inspect
import json
import logging
import random
from typing import Iterable, Type

from aiohttp import hdrs, web

from .protocol import IFRAME_HTML
from .session import SessionManager
from .transports import transport_handlers
from .transports.base import Transport
from .transports.rawwebsocket import RawWebSocketTransport
from .transports.utils import CACHE_CONTROL, cache_headers, cors_headers, session_cookie


log = logging.getLogger("sockjs")


def get_manager(name, app) -> SessionManager:
    return app["__sockjs_managers__"][name]


def _gen_endpoint_name():
    return "n" + str(random.randint(1000, 9999))


def add_endpoint(
    app: web.Application,
    handler,
    *,
    name="",
    prefix="/sockjs",
    manager=None,
    disable_transports=(),
    sockjs_cdn="https://cdn.jsdelivr.net/npm/sockjs-client@1/dist/sockjs.min.js",  # noqa
    cookie_needed=True
):
    assert callable(handler), handler
    if not asyncio.iscoroutinefunction(handler) and not inspect.isgeneratorfunction(
        handler
    ):
        sync_handler = handler

        async def handler(msg, session):
            return sync_handler(msg, session)

    router = app.router

    if not name:
        name = _gen_endpoint_name()

    # set session manager
    if manager is None:
        manager = SessionManager(name, app, handler)

    if manager.name != name:
        raise ValueError("Session manage must have same name as sockjs route")

    managers = app.setdefault("__sockjs_managers__", {})
    if name in managers:
        raise ValueError('SockJS "%s" route already registered' % name)

    managers[name] = manager

    # register routes
    route = SockJSRoute(
        name,
        manager,
        sockjs_cdn,
        transport_handlers,
        disable_transports,
        cookie_needed,
    )

    prefix = prefix.rstrip("/")
    route_name = "sockjs-url-%s-greeting" % name
    router.add_route(hdrs.METH_GET, prefix, route.greeting, name=route_name)

    route_name = "sockjs-url-%s" % name
    router.add_route(hdrs.METH_GET, "%s/" % prefix, route.greeting, name=route_name)

    route_name = "sockjs-%s" % name
    router.add_route(
        hdrs.METH_ANY,
        "%s/{server}/{session}/{transport}" % prefix,
        route.handler,
        name=route_name,
    )

    route_name = "sockjs-websocket-%s" % name
    router.add_route(
        hdrs.METH_GET, "%s/websocket" % prefix, route.websocket, name=route_name
    )

    router.add_route(
        hdrs.METH_GET, "%s/info" % prefix, route.info, name="sockjs-info-%s" % name
    )
    router.add_route(
        hdrs.METH_OPTIONS,
        "%s/info" % prefix,
        route.info_options,
        name="sockjs-info-options-%s" % name,
    )

    route_name = "sockjs-iframe-%s" % name
    router.add_route(
        hdrs.METH_GET, "%s/iframe.html" % prefix, route.iframe, name=route_name
    )

    route_name = "sockjs-iframe-ver-%s" % name
    router.add_route(
        hdrs.METH_GET, "%s/iframe{version}.html" % prefix, route.iframe, name=route_name
    )

    app.on_cleanup.append(manager.stop)


class SockJSRoute:
    def __init__(
        self,
        name: str,
        manager: SessionManager,
        sockjs_cdn: str,
        handlers,
        disable_transports: Iterable[str],
        cookie_needed=True,
    ):
        self.name = name
        self.manager = manager
        self.handlers = handlers
        self.disable_transports = set(disable_transports)
        self.cookie_needed = cookie_needed
        self.iframe_html = (IFRAME_HTML % sockjs_cdn).encode("utf-8")
        self.iframe_html_hxd = hashlib.md5(self.iframe_html).hexdigest()

    async def handler(self, request):
        info = request.match_info

        # lookup transport
        tid = info["transport"]

        if tid not in self.handlers or tid in self.disable_transports:
            return web.HTTPNotFound()

        transport: Type[Transport] = self.handlers[tid]

        # session
        manager = self.manager
        if not manager.started:
            manager.start()

        sid = info["session"]
        if not sid or "." in sid or "." in info["server"]:
            return web.HTTPNotFound()

        try:
            session = transport.get_session(manager, sid)
        except KeyError:
            return web.HTTPNotFound(headers=session_cookie(request))

        t = transport(manager, session, request)
        try:
            return await t.process()
        except asyncio.CancelledError:
            raise
        except web.HTTPException as exc:
            return exc
        except Exception:
            log.exception("Exception in transport: %s" % tid)
            if manager.is_acquired(session):
                await manager.release(session)
            return web.HTTPInternalServerError()

    async def websocket(self, request):
        if not self.manager.started:
            self.manager.start()

        # session
        sid = "%0.9d" % random.randint(1, 2147483647)
        session = self.manager.get(sid, True)

        transport = RawWebSocketTransport(self.manager, session, request)
        try:
            return await transport.process()
        except asyncio.CancelledError:
            raise
        except web.HTTPException as exc:
            return exc

    async def info(self, request):
        resp = web.Response()
        resp.headers[hdrs.CONTENT_TYPE] = "application/json;charset=UTF-8"
        resp.headers[hdrs.CACHE_CONTROL] = CACHE_CONTROL
        resp.headers.extend(cors_headers(request.headers))

        info = {
            "entropy": random.randint(1, 2147483647),
            "websocket": "websocket" not in self.disable_transports,
            "cookie_needed": self.cookie_needed,
            "origins": ["*:*"],
        }
        resp.text = json.dumps(info)
        return resp

    async def info_options(self, request):
        resp = web.Response(status=204)
        resp.headers[hdrs.CONTENT_TYPE] = "application/json;charset=UTF-8"
        resp.headers[hdrs.CACHE_CONTROL] = CACHE_CONTROL
        resp.headers[hdrs.ACCESS_CONTROL_ALLOW_METHODS] = "OPTIONS, GET"
        resp.headers.extend(cors_headers(request.headers))
        resp.headers.extend(cache_headers())
        resp.headers.extend(session_cookie(request))
        return resp

    async def iframe(self, request):
        cached = request.headers.get(hdrs.IF_NONE_MATCH)
        if cached:
            response = web.Response(status=304)
            response.headers[hdrs.CONTENT_TYPE] = ""
            response.headers.extend(cache_headers())
            return response

        headers = (
            (hdrs.CONTENT_TYPE, "text/html;charset=UTF-8"),
            (hdrs.ETAG, self.iframe_html_hxd),
        )
        headers += cache_headers()
        return web.Response(body=self.iframe_html, headers=headers)

    async def greeting(self, request):
        return web.Response(
            body=b"Welcome to SockJS!\n",
            headers=((hdrs.CONTENT_TYPE, "text/plain; charset=UTF-8"),),
        )
