from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest

from pyramid_sockjs import protocol

from base import BaseTestCase, SocketMock


class BaseSockjs(BaseTestCase):

    def make_one(self):
        from pyramid_sockjs.route import SockJSRoute
        from pyramid_sockjs.session import SessionManager

        sm = SessionManager('sm', self.registry)
        return SockJSRoute('sm', sm, 'http:sockjs-cdn', ())


class TestSockJSRoute(BaseSockjs):

    def test_info(self):
        route = self.make_one()

        response = route.info(self.request)
        info = protocol.decode(response.body)

        self.assertTrue(info['websocket'])
        self.assertTrue(info['cookie_needed'])

    def test_info_entropy(self):
        route = self.make_one()

        response = route.info(self.request)
        entropy1 = protocol.decode(response.body)['entropy']

        response = route.info(self.request)
        entropy2 = protocol.decode(response.body)['entropy']

        self.assertFalse(entropy1 == entropy2)

    def test_info_options(self):
        route = self.make_one()

        self.request.method = 'OPTIONS'
        response = route.info(self.request)

        self.assertEqual(response.status, '204 No Content')

        headers = response.headers
        self.assertIn('Access-Control-Max-Age', headers)
        self.assertIn('Cache-Control', headers)
        self.assertIn('Expires', headers)
        self.assertIn('Set-Cookie', headers)
        self.assertIn('access-control-allow-credentials', headers)
        self.assertIn('access-control-allow-origin', headers)

    def test_greeting(self):
        route = self.make_one()

        response = route.greeting(self.request)
        self.assertEqual(response.body, 'Welcome to SockJS!\n')

    def test_iframe(self):
        route = self.make_one()

        response = route.iframe(self.request)
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

        self.assertEqual(response.body, text)
        self.assertIn('ETag', response.headers)

    def test_iframe_cache(self):
        route = self.make_one()

        self.request.environ['HTTP_IF_NONE_MATCH'] = 'test'
        response = route.iframe(self.request)

        self.assertEqual(response.status, '304 Not Modified')

    def test_handler_unknown_transport(self):
        route = self.make_one()

        self.request.matchdict = {'transport': 'unknown'}
        res = route.handler(self.request)
        self.assertIsInstance(res, HTTPNotFound)

    def test_handler_emptry_session(self):
        route = self.make_one()
        self.request.matchdict = {'transport': 'websocket', 'session': ''}
        self.assertIsInstance(route.handler(self.request), HTTPNotFound)

    def test_handler_bad_session_id(self):
        route = self.make_one()

        self.request.matchdict = {'transport': 'websocket',
                                  'session': 'test.1', 'server': '000'}
        self.assertIsInstance(route.handler(self.request), HTTPNotFound)

    def test_handler_bad_server_id(self):
        route = self.make_one()

        self.request.matchdict = {'transport': 'websocket',
                                  'session': 'test', 'server': 'test.1'}
        self.assertIsInstance(route.handler(self.request), HTTPNotFound)

    def test_new_session_before_read(self):
        route = self.make_one()

        self.request.matchdict = {
            'transport': 'xhr_send', 'session': 'session', 'server': '000'}
        res = route.handler(self.request)
        self.assertIsInstance(res, HTTPNotFound)

    def test_transport(self):
        route = self.make_one()

        self.request.matchdict = {
            'transport': 'xhr', 'session': 'session', 'server': '000'}
        res = route.handler(self.request)
        self.assertIn('wsgi.sockjs_session', self.request.environ)

        from pyramid_sockjs.session import Session
        self.assertIsInstance(
            self.request.environ['wsgi.sockjs_session'], Session)

    def test_fail_transport(self):
        from pyramid_sockjs.transports import handlers
        def fail(session, request):
            raise Exception('Error')

        handlers['test'] = (True, fail)

        route = self.make_one()

        self.request.matchdict = {
            'transport': 'test', 'session': 'session', 'server': '000'}
        res = route.handler(self.request)
        self.assertIsInstance(res, HTTPBadRequest)

        del handlers['test']

    def test_release_session_for_failed_transport(self):
        from pyramid_sockjs.transports import handlers
        def fail(session, request):
            session.acquire()
            raise Exception('Error')

        handlers['test'] = (True, fail)

        route = self.make_one()

        self.request.matchdict = {
            'transport': 'test', 'session': 'session', 'server': '000'}
        res = route.handler(self.request)

        session = route.session_manager['session']
        self.assertFalse(route.session_manager.is_acquired(session))

        del handlers['test']


class TestWebSocketRoute(BaseSockjs):

    def setUp(self):
        super(TestWebSocketRoute, self).setUp()

        # handler
        from pyramid_sockjs import route
        from pyramid_sockjs.transports import handlers
        self.orig = handlers['websocket']

        self.init = []
        def websocket(session, request):
            self.init.append(True)

        handlers['websocket'] = (True, websocket)

        # init
        self.raise_init = False
        def init_websocket(request):
            if self.raise_init:
                return HTTPNotFound('error')

        self.init_orig = route.init_websocket
        route.init_websocket = init_websocket

    def tearDown(self):
        super(TestWebSocketRoute, self).tearDown()

        from pyramid_sockjs import route
        from pyramid_sockjs.transports import handlers

        handlers['websocket'] = self.orig
        route.init_websocket = self.init_orig

    def test_websocket_init(self):
        route = self.make_one()

        self.request.matchdict = {
            'transport': 'websocket', 'session': 'session', 'server': '000'}

        route.handler(self.request)
        self.assertTrue(self.init[0])

    def test_websocket_fail_init(self):
        route = self.make_one()

        self.request.matchdict = {
            'transport': 'websocket', 'session': 'session', 'server': '000'}

        self.raise_init = True
        res = route.handler(self.request)
        self.assertIsInstance(res, HTTPNotFound)

    def test_websocket_old_versions(self):
        route = self.make_one()

        self.request.environ['HTTP_ORIGIN'] = 'origin'
        self.request.matchdict = {
            'transport': 'websocket', 'session': 'session', 'server': '000'}

        res = route.handler(self.request)
        self.assertIsInstance(res, HTTPNotFound)

    def test_raw_websocket_old_versions(self):
        route = self.make_one()

        self.request.environ['HTTP_ORIGIN'] = 'origin'

        res = route.websocket(self.request)
        self.assertIsInstance(res, HTTPNotFound)

    def test_raw_websocket(self):
        from pyramid_sockjs.transports.websocket import WebSocketResponse

        route = self.make_one()

        self.request.environ['wsgi.websocket'] = object()
        res = route.websocket(self.request)
        self.assertIsInstance(res, WebSocketResponse)

    def test_raw_websocket_fail(self):
        route = self.make_one()

        self.raise_init = True
        res = route.websocket(self.request)
        self.assertIsInstance(res, HTTPNotFound)
