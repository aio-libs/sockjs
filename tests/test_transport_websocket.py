import asyncio
import datetime
from asyncio import Future
from unittest import mock

import pytest
from aiohttp import WSMessage, WSMsgType
from aiohttp.test_utils import make_mocked_coro

from sockjs import MsgType, Session, Frame
from sockjs.protocol import SockjsMessage
from sockjs.transports import WebSocketTransport


@pytest.fixture
def make_transport(make_manager, make_request, make_handler, make_fut):
    def maker(method="GET", path="/", query_params=None, handler=None):
        handler = handler or make_handler(None)
        manager = make_manager(handler)
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        session = manager.get("TestSessionWebsocket", create=True)
        session.get_frame = make_fut((Frame.CLOSE, ""))
        return WebSocketTransport(manager, session, request)

    return maker


async def xtest_process_release_acquire_and_remote_closed(make_transport):
    transp = make_transport()
    transp.session.interrupted = False
    transp.manager.acquire = make_mocked_coro()
    transp.manager.release = make_mocked_coro()
    transp.manager.remote_closed = make_mocked_coro()

    resp = await transp.process()
    await transp.manager.clear()

    assert resp.status == 101
    assert resp.headers.get("upgrade", "").lower() == "websocket"
    assert resp.headers.get("connection", "").lower() == "upgrade"

    assert transp.manager.remote_closed.called
    assert transp.manager.acquire.called
    assert transp.manager.release.called


async def test_server_close(app, make_manager, make_request):
    reached_closed = False

    loop = asyncio.get_running_loop()

    async def handler(manager, session: Session, msg: SockjsMessage):
        nonlocal reached_closed
        if msg.type == MsgType.OPEN:
            # To reproduce the ordering which makes the issue
            loop.call_later(0.05, session.close)
        elif msg.type == MsgType.MESSAGE:
            # To reproduce the ordering which makes the issue
            loop.call_later(0.05, session.close)
        elif msg.type == MsgType.CLOSED:
            reached_closed = True

    app.freeze()

    request = make_request("GET", "/")
    manager = make_manager(handler)
    session = manager.get("test", create=True)

    transp = WebSocketTransport(manager, session, request)
    await transp.process()

    assert reached_closed is False
    assert session.expires
    assert not session.expired
    session.expires = datetime.datetime.now()
    await manager._gc_expired_sessions()

    assert reached_closed is True


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

    await transp.client(ws)

    assert result[0][0].data == "single_msg"
    assert result[1][0].data == "msg1"
    assert result[2][0].data == "msg2"
