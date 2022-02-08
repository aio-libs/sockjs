from unittest import mock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_coro

from sockjs import protocol
from sockjs.transports import base


class FakeStreamingTransport(base.StreamingTransport):
    async def _send(self, text: str):
        return await super()._send(text + "\n")

    async def process(self):
        raise NotImplementedError


@pytest.fixture
def make_transport(make_manager, make_request, make_handler, make_fut):
    def maker(method="GET", path="/", query_params=None):
        handler = make_handler(None)
        manager = make_manager(handler)
        request = make_request(method, path, query_params=query_params)
        request.app.freeze()
        session = manager.get("TestSessionStreaming", create=True)
        return FakeStreamingTransport(manager, session, request)

    return maker


async def test_streaming_send(make_transport):
    trans = make_transport()

    resp = trans.response = mock.Mock()
    resp.write = make_mocked_coro(None)
    stop = await trans._send("text data")
    assert not stop
    assert trans.size == len(b"text data\n")
    resp.write.assert_called_with(b"text data\n")

    trans.maxsize = 1
    stop = await trans._send("text data")
    assert stop


async def test_handle_session_interrupted(make_transport, make_fut):
    trans = make_transport()
    trans.session.interrupted = True
    trans._send = make_fut(1)
    trans.response = web.StreamResponse()
    await trans.handle_session()
    trans._send.assert_called_with('c[1002,"Connection interrupted"]')


async def test_handle_session_closing(make_transport, make_fut):
    trans = make_transport()
    trans._send = make_fut(1)
    trans.session.interrupted = False
    trans.session.state = protocol.STATE_CLOSING
    trans.session._remote_closed = make_fut(1)
    trans.response = web.StreamResponse()
    await trans.handle_session()
    trans.session._remote_closed.assert_called_with()
    trans._send.assert_called_with('c[3000,"Go away!"]')


async def test_handle_session_closed(make_transport, make_fut):
    trans = make_transport()
    trans._send = make_fut(1)
    trans.session.interrupted = False
    trans.session.state = protocol.STATE_CLOSED
    trans.session._remote_closed = make_fut(1)
    trans.response = web.StreamResponse()
    await trans.handle_session()
    trans.session._remote_closed.assert_called_with()
    trans._send.assert_called_with('c[3000,"Go away!"]')


# async def test_session_has_request(make_transport, make_fut):
#     transp = make_transport(method="POST")
#     session = transp.session
#     session._remote_messages = make_fut(1)
#     assert session.request is None
#     await transp.process()
#     assert isinstance(session.request, web.Request)
