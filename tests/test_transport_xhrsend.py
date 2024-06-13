import pytest
from aiohttp import web

from sockjs.transports import xhr_pooling


@pytest.fixture
def make_transport(make_manager, make_request, make_handler, make_fut):
    def maker(method="GET", path="/", query_params=None):
        handler = make_handler(None)
        manager = make_manager(handler)
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        session = manager.get("TestSessionXhrSend", create=True)
        return xhr_pooling.XHRSendTransport(manager, session, request)

    return maker


async def test_not_supported_meth(make_transport):
    transp = make_transport(method="PUT")
    with pytest.raises(web.HTTPForbidden):
        await transp.process()


async def xtest_no_payload(make_transport, make_fut):
    transp = make_transport()
    transp.request.read = make_fut(b"")
    resp = await transp.process()
    assert resp.status == 500


async def xtest_bad_json(make_transport, make_fut):
    transp = make_transport()
    transp.request.read = make_fut(b"{]")
    resp = await transp.process()
    assert resp.status == 500


async def xtest_post_message(make_transport, make_fut):
    transp = make_transport()
    transp.manager.remote_messages = make_fut(1)
    transp.request.read = make_fut(b'["msg1","msg2"]')
    resp = await transp.process()
    assert resp.status == 204
    transp.manager.remote_messages.assert_called_with(["msg1", "msg2"])


async def test_options(make_transport):
    transp = make_transport(method="OPTIONS")
    resp = await transp.process()
    assert resp.status == 204
