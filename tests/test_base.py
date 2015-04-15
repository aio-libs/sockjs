import asyncio
import unittest
import urllib.parse
from unittest import mock
from aiohttp import web, CIMultiDict
from aiohttp.protocol import RawRequestMessage, HttpVersion11


class TestCase(unittest.TestCase):

    TRANSPORT_CLASS = None

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()

    def make_request(self, method, path,
                     query_params={}, headers=None, match_info=None):
        if query_params:
            path = '%s?%s' % (path, urllib.parse.urlencode(query_params))

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
        message = RawRequestMessage(
            method, path, HttpVersion11, headers, False, False)
        self.payload = mock.Mock()
        self.transport = mock.Mock()
        self.reader = mock.Mock()
        self.writer = mock.Mock()
        self.app.loop = self.loop
        req = web.Request(self.app, message, self.payload,
                          self.transport, self.reader, self.writer)
        req._match_info = match_info
        return req

    def make_fut(self, result, makemock=True):
        fut = asyncio.Future(loop=self.loop)
        fut.set_result(result)

        if makemock:
            m = mock.Mock()
            m.return_value = fut
            return m
        else:
            return fut

    def make_transport(self, method='GET', path='/', query_params={}):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = self.make_fut(1)
        request = self.make_request(method, path, query_params=query_params)
        return self.TRANSPORT_CLASS(manager, session, request)
