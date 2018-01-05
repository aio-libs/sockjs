from unittest import mock

import pytest

from sockjs.transports import EventsourceTransport


@pytest.fixture
def make_transport(make_request, make_fut):
    def maker(method='GET', path='/', query_params={}):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = make_fut(1)
        request = make_request(method, path, query_params=query_params)
        return EventsourceTransport(manager, session, request)

    return maker


def test_streaming_send(make_transport):
    trans = make_transport()

    resp = trans.response = mock.Mock()
    stop = trans.send('text data')
    resp.write.assert_called_with(b'data: text data\r\n\r\n')
    assert not stop
    assert trans.size == len(b'data: text data\r\n\r\n')

    trans.maxsize = 1
    stop = trans.send('text data')
    assert stop


async def test_process(make_transport, make_fut):
    transp = make_transport()
    transp.handle_session = make_fut(1)
    resp = await transp.process()
    assert transp.handle_session.called
    assert resp.status == 200
