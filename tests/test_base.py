import asyncio
import unittest
import urllib.parse
from unittest import mock

from aiohttp import web, CIMultiDict
from aiohttp.protocol import RawRequestMessage, HttpVersion11
from sockjs import session, route, transports


def make_raw_request_message(method, path, headers, version=HttpVersion11,
                             should_close=False, compression=False):
    raw_headers = [(k.encode('utf-8'), v.encode('utf-8'))
                   for k, v in headers.items()]
    try:
        message = RawRequestMessage(method=method, path=path, headers=headers,
                                    raw_headers=raw_headers,
                                    version=version, should_close=should_close,
                                    compression=compression)
    except TypeError:  # aiohttp < 0.21.x
        message = RawRequestMessage(method=method, path=path, headers=headers,
                                    version=version, should_close=should_close,
                                    compression=compression)
    return message


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
        message = make_raw_request_message(method, path, headers)
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


class BaseSockjs(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)

        self.app = web.Application(loop=self.loop)

    def tearDown(self):
        self.loop.close()

    def make_handler(self, result, coro=True):

        output = result

        def handler(msg, s):
            output.append(output)

        if coro:
            return asyncio.coroutine(handler)
        else:
            return handler

    def make_route(self, handlers=transports.handlers):
        handler = self.make_handler([])
        sm = session.SessionManager('sm', self.app, handler, loop=self.loop)
        return route.SockJSRoute(
            'sm', sm, 'http:sockjs-cdn', handlers, (), True)

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
        message = make_raw_request_message(method, path, headers)
        self.payload = mock.Mock()
        self.transport = mock.Mock()
        self.reader = mock.Mock()
        self.writer = mock.Mock()
        self.app.loop = self.loop
        req = web.Request(self.app, message, self.payload,
                          self.transport, self.reader, self.writer)
        req._match_info = match_info
        return req
