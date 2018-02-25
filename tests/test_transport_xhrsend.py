from unittest import mock

import pytest

from sockjs.transports import xhrsend


@pytest.fixture
def make_transport(make_request, make_fut):
    def maker(method='GET', path='/', query_params={}):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = make_fut(1)
        request = make_request(method, path, query_params=query_params)
        return xhrsend.XHRSendTransport(manager, session, request)

    return maker


async def test_not_supported_meth(make_transport):
    transp = make_transport(method='PUT')
    resp = await transp.process()
    assert resp.status == 403


async def test_no_payload(make_transport, make_fut):
    transp = make_transport()
    with pytest.warns(DeprecationWarning):
        transp.request.read = make_fut(b'')
    resp = await transp.process()
    assert resp.status == 500


async def test_bad_json(make_transport, make_fut):
    transp = make_transport()
    with pytest.warns(DeprecationWarning):
        transp.request.read = make_fut(b'{]')
    resp = await transp.process()
    assert resp.status == 500


async def test_post_message(make_transport, make_fut):
    transp = make_transport()
    transp.session._remote_messages = make_fut(1)
    with pytest.warns(DeprecationWarning):
        transp.request.read = make_fut(b'["msg1","msg2"]')
    resp = await transp.process()
    assert resp.status == 204
    transp.session._remote_messages.assert_called_with(['msg1', 'msg2'])


async def test_OPTIONS(make_transport):
    transp = make_transport(method='OPTIONS')
    resp = await transp.process()
    assert resp.status == 204
