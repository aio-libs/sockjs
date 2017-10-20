import asyncio

from unittest import mock

import pytest

from aiohttp.test_utils import make_mocked_coro

from sockjs import Session, SessionManager, MSG_OPEN, MSG_CLOSED, MSG_MESSAGE
from sockjs.protocol import FRAME_CLOSE
from sockjs.transports import WebSocketTransport


@pytest.fixture
def make_transport(make_request, make_fut):
    def maker(method='GET', path='/', query_params={}):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = make_fut(1)
        session._wait = make_fut((FRAME_CLOSE, ''))

        request = make_request(method, path, query_params=query_params)
        return WebSocketTransport(manager, session, request)

    return maker


@asyncio.coroutine
def test_process_release_acquire_and_remote_closed(make_transport):
    transp = make_transport()
    transp.session.interrupted = False
    transp.manager.acquire = make_mocked_coro()
    transp.manager.release = make_mocked_coro()
    resp = yield from transp.process()
    assert resp.status == 101
    assert resp.headers.get('upgrade', '').lower() == 'websocket'
    assert resp.headers.get('connection', '').lower() == 'upgrade'

    transp.session._remote_closed.assert_called_once_with()
    assert transp.manager.acquire.called
    assert transp.manager.release.called

@asyncio.coroutine
def test_server_close(app, loop, make_manager, make_request):
    # Issue #161
    reached_closed = False

    @asyncio.coroutine
    def handler(msg, session):
        nonlocal reached_closed
        if msg.tp == MSG_OPEN:
            asyncio.ensure_future(session._remote_message('TESTMSG'), loop=loop)
            pass
        elif msg.tp == MSG_MESSAGE:
            # To reproduce the ordering which makes the issue
            loop.call_later(0.05, session.close)
        elif msg.tp == MSG_CLOSED:
            reached_closed = True

    request = make_request('GET', '/', query_params={})
    manager = SessionManager('sm', app, handler, loop=loop, debug=True)
    session = manager.get('test', create=True)
    transp = WebSocketTransport(manager, session, request)
    resp = yield from transp.process()
    assert reached_closed


