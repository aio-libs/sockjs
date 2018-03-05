from unittest import mock

import pytest

from aiohttp.test_utils import make_mocked_coro

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
        request.app.freeze()
        return WebSocketTransport(manager, session, request)

    return maker


@pytest.mark.xfail
async def test_process_release_acquire_and_remote_closed(make_transport):
    transp = make_transport()
    transp.session.interrupted = False
    transp.manager.acquire = make_mocked_coro()
    transp.manager.release = make_mocked_coro()
    resp = await transp.process()
    assert resp.status == 101
    assert resp.headers.get('upgrade', '').lower() == 'websocket'
    assert resp.headers.get('connection', '').lower() == 'upgrade'

    transp.session._remote_closed.assert_called_once_with()
    assert transp.manager.acquire.called
    assert transp.manager.release.called
