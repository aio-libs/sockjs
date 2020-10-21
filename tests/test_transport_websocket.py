import asyncio
from asyncio import Future
from unittest import mock

from aiohttp import web, WSMessage, WSMsgType

import pytest

from aiohttp.test_utils import make_mocked_coro

from sockjs import SessionManager, MSG_OPEN, MSG_CLOSED, MSG_MESSAGE
from sockjs.protocol import FRAME_CLOSE
from sockjs.transports import WebSocketTransport


@pytest.fixture
def make_transport(make_manager, make_request, make_handler, make_fut):
    def maker(method="GET", path="/", query_params={}, handler=None):
        handler = handler or make_handler(None)
        manager = make_manager(handler)
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        session = manager.get("TestSessionWebsocket", create=True, request=request)
        session._wait = make_fut((FRAME_CLOSE, ""))
        return WebSocketTransport(manager, session, request)

    return maker


async def xtest_process_release_acquire_and_remote_closed(make_transport):
    transp = make_transport()
    transp.session.interrupted = False
    transp.manager.acquire = make_mocked_coro()
    transp.manager.release = make_mocked_coro()
    resp = await transp.process()
    await transp.manager.clear()

    assert resp.status == 101
    assert resp.headers.get("upgrade", "").lower() == "websocket"
    assert resp.headers.get("connection", "").lower() == "upgrade"

    transp.session._remote_closed.assert_called_once_with()
    assert transp.manager.acquire.called
    assert transp.manager.release.called


async def test_server_close(app, make_manager, make_request):
    reached_closed = False

    loop = asyncio.get_event_loop()

    async def handler(msg, session):
        nonlocal reached_closed
        if msg.tp == MSG_OPEN:
            asyncio.ensure_future(session._remote_message("TESTMSG"))
            pass

        elif msg.tp == MSG_MESSAGE:
            # To reproduce the ordering which makes the issue
            loop.call_later(0.05, session.close)
        elif msg.tp == MSG_CLOSED:
            reached_closed = True

    app.freeze()

    request = make_request("GET", "/", query_params={})
    manager = SessionManager("sm", app, handler, debug=True)
    session = manager.get("test", create=True)

    transp = WebSocketTransport(manager, session, request)
    await transp.process()

    assert reached_closed is True


async def test_session_has_request(make_transport, make_fut):
    transp = make_transport(method="POST")
    assert isinstance(transp.session.request, web.Request)


async def test_frames(make_transport, make_handler):
    result = []
    handler = make_handler(result)
    transp = make_transport(handler=handler)

    empty_message = Future()
    empty_message.set_result(WSMessage(type=WSMsgType.text, data="", extra=""))

    empty_frame = Future()
    empty_frame.set_result(WSMessage(type=WSMsgType.text, data="[]", extra=""))

    single_msg_frame = Future()
    single_msg_frame.set_result(
        WSMessage(type=WSMsgType.text, data='"single_msg"', extra="")
    )

    multi_msg_frame = Future()
    multi_msg_frame.set_result(
        WSMessage(type=WSMsgType.text, data='["msg1", "msg2"]', extra="")
    )

    close_frame = Future()
    close_frame.set_result(WSMessage(type=WSMsgType.closed, data="", extra=""))

    ws = mock.Mock()
    ws.receive.side_effect = [
        empty_message,
        empty_frame,
        single_msg_frame,
        multi_msg_frame,
        close_frame,
    ]

    session = transp.session
    await transp.client(ws, session)

    assert result[0][0].data == "single_msg"
    assert result[1][0].data == "msg1"
    assert result[2][0].data == "msg2"
