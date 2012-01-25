from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest

from .base import BaseTestCase, SocketMock


class BaseSockjs(BaseTestCase):

    def make_one(self):
        from pyramid_sockjs.route import SockJSRoute
        from pyramid_sockjs.session import SessionManager

        sm = SessionManager('sm', self.registry)
        return SockJSRoute('sm', sm, 'http:sockjs-cdn')


class TestSockJSRoute(BaseSockjs):

    def test_info(self):
        route = self.make_one()

        response = route.info(self.request)
        self.assertEqual(response.body, '[]')

        s = route.session_manager.acquire('id', True)
        response = route.info(self.request)
        self.assertEqual(response.body, '["id=\'id\' disconnected hits=1"]')

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

    def test_handler_unknown_transport(self):
        route = self.make_one()

        self.request.matchdict = {'transport': 'unknown'}
        res = route.handler(self.request)
        self.assertIsInstance(res, HTTPNotFound)

    def test_new_session_before_read(self):
        route = self.make_one()

        self.request.matchdict = {
            'transport': 'xhr_send', 'session': 'session'}
        res = route.handler(self.request)
        self.assertIsInstance(res, HTTPNotFound)

    def test_transport(self):
        route = self.make_one()

        self.request.matchdict = {
            'transport': 'xhr', 'session': 'session'}
        res = route.handler(self.request)
        self.assertIn('wsgi.sockjs_session', self.request.environ)

        from pyramid_sockjs.session import Session
        self.assertIsInstance(
            self.request.environ['wsgi.sockjs_session'], Session)

    def test_fail_transport(self):
        from pyramid_sockjs.route import handler_types
        def fail(session, request):
            raise Exception('Error')

        handler_types['test'] = (True, fail)

        route = self.make_one()

        self.request.matchdict = {
            'transport': 'test', 'session': 'session'}
        res = route.handler(self.request)
        self.assertIsInstance(res, HTTPBadRequest)

        del handler_types['test']


class TestWebSocketRoute(BaseSockjs):

    def setUp(self):
        super(TestWebSocketRoute, self).setUp()

        # handler
        from pyramid_sockjs import route
        self.orig = route.handler_types['websocket']

        self.init = []
        def websocket(session, request):
            self.init.append(True)

        route.handler_types['websocket'] = (True, websocket)

        # init
        self.raise_init = False
        def init_websocket(request):
            if self.raise_init:
                raise Exception('error')

        self.init_orig = route.init_websocket
        route.init_websocket = init_websocket

    def tearDown(self):
        super(TestWebSocketRoute, self).tearDown()

        from pyramid_sockjs import route
        route.handler_types['websocket'] = self.orig
        route.init_websocket = self.init_orig

    def test_websocket_init(self):
        route = self.make_one()

        self.request.matchdict = {
            'transport': 'websocket', 'session': 'session'}

        route.handler(self.request)
        self.assertTrue(self.init[0])

    def test_websocket_fail_init(self):
        route = self.make_one()

        self.request.matchdict = {
            'transport': 'websocket', 'session': 'session'}

        self.raise_init = True
        res = route.handler(self.request)
        self.assertIsInstance(res, HTTPBadRequest)
