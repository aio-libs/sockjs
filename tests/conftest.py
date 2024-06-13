import asyncio
from typing import Optional
from unittest import mock

import aiohttp_cors
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, make_mocked_coro, make_mocked_request
from aiohttp.web_urldispatcher import UrlMappingMatchInfo
from multidict import CIMultiDict
from yarl import URL

from sockjs import Session, SessionManager, add_endpoint, transports
from sockjs.route import SockJSRoute


@pytest.fixture(name="app")
def app_fixture():
    return web.Application()


@pytest.fixture
def make_fut():
    def maker(val, makemock=True):
        fut = asyncio.Future()
        fut.set_result(val)

        if makemock:
            m = mock.Mock()
            m.return_value = fut
            return m
        else:
            return fut

    return maker


@pytest.fixture
def make_handler():
    def maker(result, exc=False):
        if result is None:
            result = []
        output = result

        async def handler(manager, s, msg):
            if exc:
                raise ValueError((msg, s))
            output.append((msg, s))

        return handler

    return maker


@pytest.fixture
def make_request(app):
    def maker(method, path, query_params=None, headers=None, match_info=None):
        path = URL(path)
        if query_params:
            path = path.with_query(query_params)

        if headers is None:
            headers = CIMultiDict(
                {
                    "HOST": "server.example.com",
                    "UPGRADE": "websocket",
                    "CONNECTION": "Upgrade",
                    "SEC-WEBSOCKET-KEY": "dGhlIHNhbXBsZSBub25jZQ==",
                    "ORIGIN": "http://example.com",
                    "SEC-WEBSOCKET-PROTOCOL": "chat, superchat",
                    "SEC-WEBSOCKET-VERSION": "13",
                }
            )

        writer = mock.Mock()
        writer.write_headers = make_mocked_coro(None)
        writer.write = make_mocked_coro(None)
        writer.drain = make_mocked_coro(None)
        transport = mock.Mock()
        transport._drain_helper = make_mocked_coro()
        loop = asyncio.get_event_loop()
        ret = make_mocked_request(
            method, str(path), headers, writer=writer, transport=transport, loop=loop
        )

        if match_info is None:
            match_info = UrlMappingMatchInfo({}, mock.Mock())
            match_info.add_app(app)
        ret._match_info = match_info
        return ret

    return maker


@pytest.fixture
def make_session(make_handler, make_request):
    def maker(
        name="test", disconnect_delay=10, manager: Optional[SessionManager] = None
    ):
        session = Session(name, disconnect_delay=disconnect_delay, debug=True)
        if manager:
            manager.sessions[session.id] = session
        return session

    return maker


@pytest.fixture
async def make_manager(app, make_handler, make_session):
    managers = []

    def maker(handler=None):
        if handler is None:
            handler = make_handler([])
        manager = SessionManager("sm", app, handler, debug=True)
        managers.append(manager)
        return manager

    yield maker

    for sm in managers:
        await sm.stop()


@pytest.fixture
def make_route(make_manager, make_handler, app):
    def maker(handlers=transports.transport_handlers):
        sm = make_manager()
        app.on_cleanup.append(sm.stop)
        return SockJSRoute("sm", sm, "http:sockjs-cdn", handlers, (), True)

    return maker


@pytest.fixture(name="test_client")
async def test_client_fixture(app, aiohttp_client, make_handler) -> TestClient:
    handler = make_handler(None)
    # Configure default CORS settings.
    cors = aiohttp_cors.setup(
        app,
        defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                max_age=31536000,
            )
        },
    )
    add_endpoint(
        app,
        handler,
        name="main",
        cors_config=cors,
    )
    return await aiohttp_client(app)
