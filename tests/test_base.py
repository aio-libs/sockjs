import asyncio
import unittest
import urllib.parse
from datetime import timedelta
from unittest import mock

from aiohttp import CIMultiDict
from aiohttp.web import Request, Application
from aiohttp.protocol import RawRequestMessage, HttpVersion11
from aiohttp.signals import Signal

from sockjs import Session, SessionManager, transports
from sockjs.route import SockJSRoute


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


class BaseTestCase(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        super().tearDown()
        self.loop.close()

    def make_request(self, method, path, query_params={}, headers=None,
                     match_info=None):
        if query_params:
            path = '%s?%s' % (path, urllib.parse.urlencode(query_params))

        # Ported from:
        # https://github.com/KeepSafe/aiohttp/blob/fa06acc2392c516491bdb25301ad3ef2b700ff5f/tests/test_web_websocket.py#L21-L45  # noqa
        self.app = mock.Mock()
        self.app._debug = False
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
        self.app.on_response_prepare = Signal(self.app)
        req = Request(self.app, message, self.payload,
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


class BaseSockjsTestCase(BaseTestCase):

    TRANSPORT_CLASS = None

    def setUp(self):
        super().setUp()
        self.app = Application(loop=self.loop)

    def make_route(self, handlers=transports.handlers):
        handler = self.make_handler([])
        sm = SessionManager('sm', self.app, handler, loop=self.loop)
        return SockJSRoute('sm', sm, 'http:sockjs-cdn', handlers, (), True)

    def make_transport(self, method='GET', path='/', query_params={}):
        manager = mock.Mock()
        session = mock.Mock()
        session._remote_closed = self.make_fut(1)
        request = self.make_request(method, path, query_params=query_params)
        return self.TRANSPORT_CLASS(manager, session, request)

    def make_session(self, name='test', timeout=timedelta(10), handler=None,
                     result=None):
        if handler is None:
            handler = self.make_handler(result)
        return Session(name, handler,
                       timeout=timeout, loop=self.loop, debug=True)

    def make_manager(self, handler=None):
        if handler is None:
            handler = self.make_handler([])
        s = self.make_session('test', handler=handler)
        return s, SessionManager(
            'sm', self.app, handler, loop=self.loop, debug=True)

    def make_handler(self, result, coro=True, exc=False):
        if result is None:
            result = []
        output = result

        def handler(msg, s):
            if exc:
                raise ValueError((msg, s))
            output.append((msg, s))

        if coro:
            return asyncio.coroutine(handler)
        else:
            return handler
