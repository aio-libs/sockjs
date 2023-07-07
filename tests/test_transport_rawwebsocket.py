from asyncio import Future
from unittest import mock

import pytest
from aiohttp import WSMessage, WSMsgType

from sockjs.exceptions import SessionIsClosed
from sockjs.protocol import Frame
from sockjs.transports.rawwebsocket import RawWebSocketTransport
from sockjs.transports.utils import cancel_tasks


@pytest.fixture
def make_transport(make_request, make_fut):
    def maker(method="GET", path="/", query_params=None):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = make_fut(1)
        session._get_frame = make_fut((Frame.CLOSE, ""))
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        return RawWebSocketTransport(manager, session, request)

    return maker


async def xtest_ticks_pong(make_transport, make_fut):
    transp = make_transport()

    pong = WSMessage(type=WSMsgType.PONG, data=b"", extra="")
    close = WSMessage(type=WSMsgType.closing, data=b"", extra="")

    future = Future()
    future.set_result(pong)

    future2 = Future()
    future2.set_result(close)

    ws = mock.Mock()
    ws.receive.side_effect = [future, future2]

    session = transp.session

    await transp.client(ws, session)
    assert session.tick.called


async def test_sends_ping(make_transport, make_fut):
    transp = make_transport()

    future = Future()
    future.set_result(False)

    ws = mock.Mock()
    ws.ping.side_effect = [future]

    hb_future = Future()
    hb_future.set_result((Frame.HEARTBEAT, b""))

    session_close_future = Future()
    session_close_future.set_exception(SessionIsClosed)

    session = mock.Mock()
    session.get_frame.side_effect = [hb_future, session_close_future]
    transp.session = session

    await transp.server(ws)
    assert ws.ping.called
    await cancel_tasks(transp._wait_pong_task)
