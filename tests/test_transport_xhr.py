from unittest import mock

import pytest

from sockjs.transports import xhr


@pytest.fixture
def make_transport(make_request, make_fut):
    def maker(method='GET', path='/', query_params={}):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = make_fut(1)
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        return xhr.XHRTransport(manager, session, request)

    return maker


async def test_process(make_transport, make_fut):
    transp = make_transport()
    transp.handle_session = make_fut(1)
    resp = await transp.process()
    assert transp.handle_session.called
    assert resp.status == 200


async def test_process_OPTIONS(make_transport):
    transp = make_transport(method='OPTIONS')
    resp = await transp.process()
    assert resp.status == 204
