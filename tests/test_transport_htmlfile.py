from unittest import mock

import pytest
from aiohttp.test_utils import make_mocked_coro

from sockjs.transports import htmlfile


@pytest.fixture
def make_transport(make_request, make_fut):
    def maker(method='GET', path='/', query_params={}):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = make_fut(1)
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        return htmlfile.HTMLFileTransport(manager, session, request)

    return maker


async def test_streaming_send(make_transport):
    trans = make_transport()

    resp = trans.response = mock.Mock()
    resp.write = make_mocked_coro(None)
    stop = await trans.send('text data')
    resp.write.assert_called_with(
        b'<script>\np("text data");\n</script>\r\n')
    assert not stop
    assert trans.size == len(b'<script>\np("text data");\n</script>\r\n')

    trans.maxsize = 1
    stop = trans.send('text data')
    assert stop


async def test_process(make_transport, make_fut):
    transp = make_transport(query_params={'c': 'calback'})
    transp.handle_session = make_fut(1)
    resp = await transp.process()
    assert transp.handle_session.called
    assert resp.status == 200


async def test_process_no_callback(make_transport):
    transp = make_transport()

    resp = await transp.process()
    assert transp.session._remote_closed.called
    assert resp.status == 500


async def test_process_bad_callback(make_transport):
    transp = make_transport(query_params={'c': 'calback!!!!'})

    resp = await transp.process()
    assert transp.session._remote_closed.called
    assert resp.status == 500
