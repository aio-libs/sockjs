import asyncio
import unittest
from unittest import mock
from aiohttp import web, CIMultiDict
from aiohttp.protocol import RawRequestMessage, HttpVersion11

from sockjs.transports import base


class TransportTestCase(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()

    def make_request(self, method, path, headers=None, match_info=None):
        self.app = mock.Mock()
        if headers is None:
            headers = CIMultiDict(
                {'HOST': 'server.example.com',
                 'UPGRADE': 'websocket',
                 'CONNECTION': 'Upgrade',
                 'SEC-WEBSOCKET-KEY': 'dGhlIHNhbXBsZSBub25jZQ==',
                 'ORIGIN': 'http://example.com',
                 'SEC-WEBSOCKET-PROTOCOL': 'chat, superchat',
                 'SEC-WEBSOCKET-VERSION': '13'})
        message = RawRequestMessage(method, path, HttpVersion11, headers,
                                    False, False)
        self.payload = mock.Mock()
        self.transport = mock.Mock()
        self.reader = mock.Mock()
        self.writer = mock.Mock()
        self.app.loop = self.loop
        req = web.Request(self.app, message, self.payload,
                          self.transport, self.reader, self.writer)
        req._match_info = match_info
        return req

    def make_streaming(self):
        manager = mock.Mock()
        session = mock.Mock()
        request = self.make_request('GET', '/')
        return base.StreamingTransport(manager, session, request)

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
        trans = self.make_streaming()

        resp = trans.response = mock.Mock()
        stop = trans.send('text data')
        self.assertFalse(stop)
        self.assertEqual(trans.size, len(b'text data\n'))
        resp.write.assert_called_with(b'text data\n')

        trans.maxsize = 1
        stop = trans.send('text data')
        self.assertTrue(stop)
