from unittest import mock
from aiohttp import web

import pytest
from aiohttp.test_utils import make_mocked_coro

from sockjs import protocol
from sockjs.transports import base


@pytest.fixture
def make_transport(make_request, make_fut):
    def maker(method='GET', path='/', query_params={}):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = make_fut(1)
        request = make_request(method, path, query_params=query_params)
        return base.StreamingTransport(manager, session, request)

    return maker


def test_transport_ctor(make_request):
    manager = object()
    session = object()
    request = make_request('GET', '/')

    transport = base.Transport(manager, session, request)
    assert transport.manager is manager
    assert transport.session is session
    assert transport.request is request


async def test_streaming_send(make_transport):
    trans = make_transport()

    resp = trans.response = mock.Mock()
    resp.write = make_mocked_coro(None)
    stop = await trans.send('text data')
    assert not stop
    assert trans.size == len(b'text data\n')
    resp.write.assert_called_with(b'text data\n')

    trans.maxsize = 1
    stop = await trans.send('text data')
    assert stop


async def test_handle_session_interrupted(make_transport, make_fut):
    trans = make_transport()
    trans.session.interrupted = True
    trans.send = make_fut(1)
    trans.response = web.StreamResponse()
    await trans.handle_session()
    trans.send.assert_called_with('c[1002,"Connection interrupted"]')


async def test_handle_session_closing(make_transport, make_fut):
    trans = make_transport()
    trans.send = make_fut(1)
    trans.session.interrupted = False
    trans.session.state = protocol.STATE_CLOSING
    trans.session._remote_closed = make_fut(1)
    trans.response = web.StreamResponse()
    await trans.handle_session()
    trans.session._remote_closed.assert_called_with()
    trans.send.assert_called_with('c[3000,"Go away!"]')


async def test_handle_session_closed(make_transport, make_fut):
    trans = make_transport()
    trans.send = make_fut(1)
    trans.session.interrupted = False
    trans.session.state = protocol.STATE_CLOSED
    trans.session._remote_closed = make_fut(1)
    trans.response = web.StreamResponse()
    await trans.handle_session()
    trans.session._remote_closed.assert_called_with()
    trans.send.assert_called_with('c[3000,"Go away!"]')
