import asyncio
import unittest
from unittest import mock

from aiohttp import web
from aiohttp import CIMultiDict
from aiohttp.protocol import RawRequestMessage, HttpVersion11
from sockjs import session, route, protocol, transports


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


class TestSockJSRoute(BaseSockjs):

    def test_info(self):
        route = self.make_route()
        request = self.make_request('GET', '/sm/')

        response = route.info(request)
        info = protocol.loads(response.body.decode('utf-8'))

        self.assertTrue(info['websocket'])
        self.assertTrue(info['cookie_needed'])

    def test_info_entropy(self):
        route = self.make_route()
        request = self.make_request('GET', '/sm/')

        response = route.info(request)
        entropy1 = protocol.loads(response.body.decode('utf-8'))['entropy']

        response = route.info(request)
        entropy2 = protocol.loads(response.body.decode('utf-8'))['entropy']

        self.assertFalse(entropy1 == entropy2)

    def test_info_options(self):
        route = self.make_route()
        request = self.make_request('OPTIONS', '/sm/')
        response = route.info_options(request)

        self.assertEqual(response.status, 204)

        headers = response.headers
        self.assertIn('Access-Control-Max-Age', headers)
        self.assertIn('Cache-Control', headers)
        self.assertIn('Expires', headers)
        self.assertIn('Set-Cookie', headers)
        self.assertIn('access-control-allow-credentials', headers)
        self.assertIn('access-control-allow-origin', headers)

    def test_greeting(self):
        route = self.make_route()
        request = self.make_request('GET', '/sm/')
        response = route.greeting(request)

        self.assertEqual(response.body, b'Welcome to SockJS!\n')

    def test_iframe(self):
        route = self.make_route()
        request = self.make_request('GET', '/sm/')

        response = route.iframe(request)
        text = """<!DOCTYPE html>
<html>
<head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <script>
    document.domain = document.domain;
    _sockjs_onload = function(){SockJS.bootstrap_iframe();};
  </script>
  <script src="http:sockjs-cdn"></script>
</head>
<body>
  <h2>Don't panic!</h2>
  <p>This is a SockJS hidden iframe. It's used for cross domain magic.</p>
</body>
</html>"""

        self.assertEqual(response.body.decode('utf-8'), text)
        self.assertIn('ETag', response.headers)

    def test_iframe_cache(self):
        route = self.make_route()
        request = self.make_request(
            'GET', '/sm/',
            headers=CIMultiDict({'IF-NONE-MATCH': 'test'}))
        response = route.iframe(request)

        self.assertEqual(response.status, 304)

    def test_handler_unknown_transport(self):
        route = self.make_route()
        request = self.make_request(
            'GET', '/sm/', match_info={'transport': 'unknown'})

        res = self.loop.run_until_complete(route.handler(request))
        self.assertIsInstance(res, web.HTTPNotFound)

    def test_handler_emptry_session(self):
        route = self.make_route()
        request = self.make_request(
            'GET', '/sm/',
            match_info={'transport': 'websocket', 'session': ''})
        res = self.loop.run_until_complete(route.handler(request))
        self.assertIsInstance(res, web.HTTPNotFound)

    def test_handler_bad_session_id(self):
        route = self.make_route()
        request = self.make_request(
            'GET', '/sm/',
            match_info={'transport': 'websocket',
                        'session': 'test.1', 'server': '000'})
        res = self.loop.run_until_complete(route.handler(request))
        self.assertIsInstance(res, web.HTTPNotFound)

    def test_handler_bad_server_id(self):
        route = self.make_route()
        request = self.make_request(
            'GET', '/sm/',
            match_info={'transport': 'websocket',
                        'session': 'test', 'server': 'test.1'})
        res = self.loop.run_until_complete(route.handler(request))
        self.assertIsInstance(res, web.HTTPNotFound)

    def test_new_session_before_read(self):
        route = self.make_route()
        request = self.make_request(
            'GET', '/sm/',
            match_info={
                'transport': 'xhr_send', 'session': 's1', 'server': '000'})
        res = self.loop.run_until_complete(route.handler(request))
        self.assertIsInstance(res, web.HTTPNotFound)

    def _test_transport(self):
        route = self.make_route()
        request = self.make_request(
            'GET', '/sm/',
            match_info={
                'transport': 'xhr', 'session': 's1', 'server': '000'})

        params = []

        class Transport:
            def __init__(self, manager, session, request):
                params.append((manager, session, request))

            def process(self):
                return web.HTTPOk()

        route = self.make_route(handlers={'test': (True, Transport)})
        res = self.loop.run_until_complete(route.handler(request))
        self.assertIsInstance(res, web.HTTPOk)
        self.assertEqual(
            params[0], (route.manager, route.manager['s1'], request))

    def test_fail_transport(self):
        request = self.make_request(
            'GET', '/sm/',
            match_info={
                'transport': 'test', 'session': 'session', 'server': '000'})

        params = []

        class Transport:
            def __init__(self, manager, session, request):
                params.append((manager, session, request))

            def process(self):
                raise Exception('Error')

        route = self.make_route(handlers={'test': (True, Transport)})
        res = self.loop.run_until_complete(route.handler(request))
        self.assertIsInstance(res, web.HTTPInternalServerError)

    def test_release_session_for_failed_transport(self):
        request = self.make_request(
            'GET', '/sm/',
            match_info={
                'transport': 'test', 'session': 's1', 'server': '000'})

        class Transport:
            def __init__(self, manager, session, request):
                self.manager = manager
                self.session = session

            def process(self):
                yield from self.manager.acquire(self.session)
                raise Exception('Error')

        route = self.make_route(handlers={'test': (True, Transport)})
        res = self.loop.run_until_complete(route.handler(request))
        self.assertIsInstance(res, web.HTTPInternalServerError)

        s1 = route.manager['s1']
        self.assertFalse(route.manager.is_acquired(s1))

    @mock.patch('sockjs.route.RawWebSocketTransport')
    def test_raw_websocket(self, ws):
        ws.return_value.process.return_value = asyncio.Future(loop=self.loop)
        ws.return_value.process.return_value.set_result(web.HTTPOk())

        route = self.make_route()
        request = self.make_request(
            'GET', '/sm/', headers=CIMultiDict({}))
        res = self.loop.run_until_complete(route.websocket(request))

        self.assertIsInstance(res, web.HTTPOk)
        self.assertTrue(ws.called)
        self.assertTrue(ws.return_value.process.called)

    def test_raw_websocket_fail(self):
        route = self.make_route()
        request = self.make_request('GET', '/sm/')
        res = self.loop.run_until_complete(route.websocket(request))
        self.assertIsInstance(res, web.HTTPNotFound)
