from pyramid.testing import DummyRequest
from pyramid.response import Response
from pyramid.httpexceptions import \
     HTTPNotFound, HTTPBadRequest, HTTPMethodNotAllowed

from base import BaseTestCase, SocketMock


class WebSoscketHandshake(BaseTestCase):

    def test_websocket_upgrade(self):
        from pyramid_sockjs.websocket import init_websocket
        request = DummyRequest()

        res = init_websocket(request)
        self.assertIsInstance(res, HTTPBadRequest)
        self.assertEqual(res.detail, 'Can "Upgrade" only to "WebSocket".')

        request.environ['HTTP_UPGRADE'] = 'ssl'

        res = init_websocket(request)
        self.assertIsInstance(res, HTTPBadRequest)
        self.assertEqual(res.detail, 'Can "Upgrade" only to "WebSocket".')

    def test_connection_upgrade(self):
        from pyramid_sockjs.websocket import init_websocket
        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'close'})

        res = init_websocket(request)
        self.assertIsInstance(res, HTTPBadRequest)
        self.assertEqual(res.detail, '"Connection" must be "Upgrade".')

    def test_websocket_version(self):
        from pyramid_sockjs.websocket import init_websocket

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade'})

        res = init_websocket(request)
        self.assertIsInstance(res, HTTPBadRequest)
        self.assertEqual(res.detail, 'Unsupported WebSocket version.')

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '5'})

        res = init_websocket(request)
        self.assertIsInstance(res, HTTPBadRequest)
        self.assertEqual(res.detail, 'Unsupported WebSocket version.')

    def test_method_type(self):
        from pyramid_sockjs.websocket import init_websocket

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8'})
        request.method = 'POST'

        res = init_websocket(request)
        self.assertIsInstance(res, Response)
        self.assertEqual(res.status, '405 Method Not Allowed')

    def test_protocol_type(self):
        from pyramid_sockjs.websocket import init_websocket

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTPS/1.1'})
        request.method = 'GET'

        res = init_websocket(request)
        self.assertIsInstance(res, HTTPBadRequest)
        self.assertEqual(res.detail, 'Protocol is not HTTP')

    def test_protocol_version(self):
        from pyramid_sockjs.websocket import init_websocket

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTP/1.0'})
        request.method = 'GET'

        res = init_websocket(request)
        self.assertIsInstance(res, HTTPBadRequest)
        self.assertEqual(res.detail, 'HTTP/1.1 is required')

    def test_websocket_key(self):
        from pyramid_sockjs.websocket import init_websocket

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTP/1.1',
                     'HTTP_SEC_WEBSOCKET_KEY': None,})
        request.method = 'GET'

        res = init_websocket(request)
        self.assertIsInstance(res, HTTPBadRequest)
        self.assertEqual(res.detail, 'HTTP_SEC_WEBSOCKET_KEY is invalid key')

    def test_gevent_wsgi_input(self):
        from pyramid_sockjs.websocket import init_websocket

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTP/1.1',
                     'HTTP_SEC_WEBSOCKET_KEY': '5Jfbk3Hf5oLcReU416OxpA==',
                     'HTTP_CONNECTION': 'keep-alive, upgrade'})
        request.method = 'GET'

        res = init_websocket(request)
        self.assertIsInstance(res, HTTPBadRequest)
        self.assertEqual(res.detail, "socket object is not available")

    def test_success(self):
        from pyramid_sockjs.websocket import init_websocket

        class WS(object):
            def __init__(self, rfile, environ):
                self.rfile = rfile
                self.environ = environ

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTP/1.1',
                     'HTTP_SEC_WEBSOCKET_KEY': '5Jfbk3Hf5oLcReU416OxpA==',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'gunicorn.socket': SocketMock()})
        request.method = 'GET'

        from pyramid_sockjs import websocket
        orig = websocket.WebSocketHybi
        websocket.WebSocketHybi = WS
        try:
            ws = init_websocket(request)
        finally:
            websocket.WebSocketHybi = orig

        environ = request.environ
        self.assertIn('wsgi.websocket_version', environ)
        self.assertEqual(environ['wsgi.websocket_version'], 'hybi-8')

        self.assertIn('wsgi.websocket', environ)
        self.assertIsInstance(environ['wsgi.websocket'], WS)

        response = request.response
        self.assertEqual(response.status, '101 Switching Protocols')
        self.assertEqual(response.headers['Upgrade'], 'websocket')
        self.assertEqual(response.headers['Connection'], 'Upgrade')
