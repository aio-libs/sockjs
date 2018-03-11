from aiohttp import web

import pytest

from sockjs.transports import xhr


@pytest.fixture
def make_transport(make_manager, make_request, make_handler, make_fut):
    def maker(method='GET', path='/', query_params={}):
        handler = make_handler(None)
        manager = make_manager(handler)
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        session = manager.get('TestSessionXhr', create=True, request=request)
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


async def test_session_has_request(make_transport, make_fut):
    transp = make_transport()
    transp.session._remote_messages = make_fut(1)
    assert isinstance(transp.session.request, web.Request)
