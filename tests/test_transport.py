from unittest import mock
from aiohttp import web

from sockjs import protocol
from sockjs.transports import base

from test_base import BaseSockjsTestCase


class TransportTestCase(BaseSockjsTestCase):

    TRANSPORT_CLASS = base.StreamingTransport

    def test_transport_ctor(self):
        manager = object()
        session = object()
        request = self.make_request('GET', '/')

        transport = base.Transport(manager, session, request)
        self.assertIs(transport.manager, manager)
        self.assertIs(transport.session, session)
        self.assertIs(transport.request, request)
        self.assertIs(transport.loop, self.loop)

    def test_streaming_send(self):
        trans = self.make_transport()

        resp = trans.response = mock.Mock()
        stop = trans.send('text data')
        self.assertFalse(stop)
        self.assertEqual(trans.size, len(b'text data\n'))
        resp.write.assert_called_with(b'text data\n')

        trans.maxsize = 1
        stop = trans.send('text data')
        self.assertTrue(stop)

    def test_handle_session_interrupted(self):
        trans = self.make_transport()
        trans.session.interrupted = True
        trans.send = self.make_fut(1)
        trans.response = web.StreamResponse()
        self.loop.run_until_complete(trans.handle_session())
        trans.send.assert_called_with('c[1002,"Connection interrupted"]')

    def test_handle_session_closing(self):
        trans = self.make_transport()
        trans.send = self.make_fut(1)
        trans.session.interrupted = False
        trans.session.state = protocol.STATE_CLOSING
        trans.session._remote_closed = self.make_fut(1)
        trans.response = web.StreamResponse()
        self.loop.run_until_complete(trans.handle_session())
        trans.session._remote_closed.assert_called_with()
        trans.send.assert_called_with('c[3000,"Go away!"]')

    def test_handle_session_closed(self):
        trans = self.make_transport()
        trans.send = self.make_fut(1)
        trans.session.interrupted = False
        trans.session.state = protocol.STATE_CLOSED
        trans.session._remote_closed = self.make_fut(1)
        trans.response = web.StreamResponse()
        self.loop.run_until_complete(trans.handle_session())
        trans.session._remote_closed.assert_called_with()
        trans.send.assert_called_with('c[3000,"Go away!"]')
