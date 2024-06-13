import asyncio
import hashlib
import inspect
import json
import logging
import random
from typing import Iterable, List, Optional, Type

from aiohttp import hdrs, web
from aiohttp.web_request import Request


try:
    from aiohttp_cors import CorsConfig
except ImportError:
    CorsConfig = None

from .protocol import IFRAME_HTML
from .session import SessionManager, HandlerType
from .transports import transport_handlers
from .transports.base import Transport
from .transports.rawwebsocket import RawWebSocketTransport
from .transports.utils import CACHE_CONTROL, cache_headers, session_cookie


log = logging.getLogger("sockjs")
ALL_METH_WO_OPTIONS = hdrs.METH_ALL - {hdrs.METH_OPTIONS}


def get_manager(name, app) -> SessionManager:
    return app["__sockjs_managers__"][name]


def _gen_endpoint_name():
    return "n" + str(random.randint(1000, 9999))


def add_endpoint(
    app: web.Application,
    handler: HandlerType,
    *,
    name="",
    prefix="/sockjs",
    manager=None,
    disable_transports=(),
    sockjs_cdn="https://cdn.jsdelivr.net/npm/sockjs-client@1/dist/sockjs.min.js",  # noqa
    cookie_needed=True,
    cors_config: Optional[CorsConfig] = None,
    heartbeat_delay=25,
    disconnect_delay=5,
    debug=False,
) -> List[web.AbstractRoute]:
    registered_routes = []

    assert callable(handler), handler
    if not asyncio.iscoroutinefunction(handler) and not inspect.isgeneratorfunction(
        handler
    ):
        sync_handler = handler

        async def handler(m, s, msg):
            return sync_handler(m, s, msg)

    router = app.router

    if not name:
        name = _gen_endpoint_name()

    # set session manager
    if manager is None:
        manager = SessionManager(
            name,
            app,
            handler,
            heartbeat_delay,
            disconnect_delay,
            debug=debug,
        )

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
    route_name = "sockjs-greeting-%s" % name
    registered_routes.append(
        router.add_route(hdrs.METH_GET, prefix, route.greeting, name=route_name)
    )

    route_name = "sockjs-greeting-ts-%s" % name
    registered_routes.append(
        router.add_route(hdrs.METH_GET, "%s/" % prefix, route.greeting, name=route_name)
    )

    resource = router.add_resource(
        "%s/{server}/{session}/{transport}" % prefix, name=f"sockjs-transport-{name}"
    )
    for method in ALL_METH_WO_OPTIONS:
        registered_routes.append(
            resource.add_route(
                method,
                route.handler,
            )
        )

    if "websocket-raw" not in route.disable_transports:
        route_name = "sockjs-websocket-%s" % name
        registered_routes.append(
            router.add_route(
                hdrs.METH_GET,
                "%s/websocket" % prefix,
                route.websocket,
                name=route_name,
            )
        )

    registered_routes.append(
        router.add_route(
            hdrs.METH_GET,
            "%s/info" % prefix,
            route.info,
            name="sockjs-info-%s" % name,
        )
    )

    route_name = "sockjs-iframe-%s" % name
    registered_routes.append(
        router.add_route(
            hdrs.METH_GET, "%s/iframe.html" % prefix, route.iframe, name=route_name
        )
    )

    route_name = "sockjs-iframe-ver-%s" % name
    registered_routes.append(
        router.add_route(
            hdrs.METH_GET,
            "%s/iframe{version}.html" % prefix,
            route.iframe,
            name=route_name,
        )
    )

    app.on_cleanup.append(manager.stop)

    if cors_config is not None:
        # Configure CORS on all routes.
        for route in registered_routes:
            cors_config.add(route)

    return registered_routes


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
        transport_names = {
            transport_class.name for transport_class in transport_handlers.values()
        }
        transport_names.add("websocket-raw")
        self._transport_names = sorted(transport_names - self.disable_transports)

    async def handler(self, request: Request):
        info = request.match_info

        # lookup transport
        t_id = info["transport"]
        transport_class: Optional[Type[Transport]] = self.handlers.get(t_id)
        if transport_class is None or transport_class.name in self.disable_transports:
            raise web.HTTPNotFound()

        # session
        manager = self.manager
        if not manager.started:
            manager.start()

        sid = info["session"]
        if not sid or "." in sid or "." in info["server"]:
            raise web.HTTPNotFound()

        try:
            session = transport_class.get_session(manager, sid)
        except KeyError:
            raise web.HTTPNotFound(headers=session_cookie(request))

        request["sockjs_transport_name"] = transport_class.name
        transport = transport_class(manager, session, request)
        try:
            return await transport.process()
        except (asyncio.CancelledError, web.HTTPException, ConnectionError) as e:
            if transport.create_session:
                await manager.remote_close(session, exc=e)
            raise
        except Exception as e:
            log.exception("Exception in transport: %s" % t_id)
            if transport.create_session:
                await manager.remote_close(session, exc=e)
            raise web.HTTPInternalServerError()
        finally:
            if transport.create_session and manager.is_acquired(session):
                await manager.remote_close(session)
                await manager.remote_closed(session)
                await manager.release(session)

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
            raise exc

    async def info(self, request):
        resp = web.Response()
        resp.headers[hdrs.CONTENT_TYPE] = "application/json;charset=UTF-8"
        resp.headers[hdrs.CACHE_CONTROL] = CACHE_CONTROL

        info = {
            "entropy": random.randint(1, 2147483647),
            "websocket": "websocket" in self._transport_names,
            "cookie_needed": self.cookie_needed,
            "origins": ["*:*"],
            "transports": self._transport_names,
        }
        resp.text = json.dumps(info)
        return resp

    async def iframe(self, request):
        cached = request.headers.get(hdrs.IF_NONE_MATCH)
        if cached:
            response = web.Response(status=304)
            response.headers[hdrs.CONTENT_TYPE] = ""
            response.headers.extend(cache_headers())
            return response

        headers = {
            hdrs.CONTENT_TYPE: "text/html;charset=UTF-8",
            hdrs.ETAG: self.iframe_html_hxd,
        }
        headers.update(dict(cache_headers()))
        return web.Response(body=self.iframe_html, headers=headers)

    async def greeting(self, request):
        return web.Response(
            body=b"Welcome to SockJS!\n",
            headers={hdrs.CONTENT_TYPE: "text/plain; charset=UTF-8"},
        )
