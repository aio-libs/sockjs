import asyncio

from aiohttp import web

import pytest

from aiohttp.test_utils import make_mocked_coro

from sockjs import SessionManager, MSG_OPEN, MSG_CLOSED, MSG_MESSAGE
from sockjs.protocol import FRAME_CLOSE
from sockjs.transports import WebSocketTransport


@pytest.fixture
def make_transport(make_manager, make_request, make_handler, make_fut):
    def maker(method='GET', path='/', query_params={}):
        handler = make_handler(None)
        manager = make_manager(handler)
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        session = manager.get('TestSessionWebsocket',
                              create=True, request=request)
        session._wait = make_fut((FRAME_CLOSE, ''))
        return WebSocketTransport(manager, session, request)

    return maker


@pytest.mark.xfail
async def test_process_release_acquire_and_remote_closed(make_transport):
    transp = make_transport()
    transp.session.interrupted = False
    transp.manager.acquire = make_mocked_coro()
    transp.manager.release = make_mocked_coro()
    resp = await transp.process()
    await transp.manager.clear()

    assert resp.status == 101
    assert resp.headers.get('upgrade', '').lower() == 'websocket'
    assert resp.headers.get('connection', '').lower() == 'upgrade'

    transp.session._remote_closed.assert_called_once_with()
    assert transp.manager.acquire.called
    assert transp.manager.release.called


async def test_server_close(app, make_manager, make_request):
    reached_closed = False

    loop = asyncio.get_event_loop()

    async def handler(msg, session):
        nonlocal reached_closed
        if msg.tp == MSG_OPEN:
            asyncio.ensure_future(session._remote_message('TESTMSG'),
                                  loop=loop)
            pass

        elif msg.tp == MSG_MESSAGE:
            # To reproduce the ordering which makes the issue
            loop.call_later(0.05, session.close)
        elif msg.tp == MSG_CLOSED:
            reached_closed = True

    app.freeze()

    request = make_request('GET', '/', query_params={}, loop=loop)
    manager = SessionManager('sm', app, handler, loop=loop, debug=True)
    session = manager.get('test', create=True)

    transp = WebSocketTransport(manager, session, request)
    await transp.process()

    assert reached_closed is True


async def test_session_has_request(make_transport, make_fut):
    transp = make_transport(method='POST')
    assert isinstance(transp.session.request, web.Request)
