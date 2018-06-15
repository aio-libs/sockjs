from unittest import mock
from asyncio import Future

import pytest

from sockjs.exceptions import SessionIsClosed
from sockjs.protocol import FRAME_CLOSE, FRAME_HEARTBEAT
from sockjs.transports.rawwebsocket import RawWebSocketTransport

from aiohttp import WSMessage, WSMsgType


@pytest.fixture
def make_transport(make_request, make_fut):
    def maker(method='GET', path='/', query_params={}):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = make_fut(1)
        session._wait = make_fut((FRAME_CLOSE, ''))
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        return RawWebSocketTransport(manager, session, request)

    return maker


async def test_ticks_pong(make_transport, make_fut):
    transp = make_transport()

    pong = WSMessage(type=WSMsgType.PONG, data=b'', extra='')
    close = WSMessage(type=WSMsgType.closing, data=b'', extra='')

    future = Future()
    future.set_result(pong)

    future2 = Future()
    future2.set_result(close)

    ws = mock.Mock()
    ws.receive.side_effect = [future, future2]

    session = transp.session

    await transp.client(ws, session)
    assert session._tick.called


async def test_sends_ping(make_transport, make_fut):
    transp = make_transport()

    future = Future()
    future.set_result(False)

    ws = mock.Mock()
    ws.ping.side_effect = [future]

    hb_future = Future()
    hb_future.set_result((FRAME_HEARTBEAT, b''))

    session_close_future = Future()
    session_close_future.set_exception(SessionIsClosed)

    session = mock.Mock()
    session._wait.side_effect = [hb_future, session_close_future]

    await transp.server(ws, session)
    assert ws.ping.called
