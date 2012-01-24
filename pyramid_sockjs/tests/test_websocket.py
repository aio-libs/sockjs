from pyramid.testing import DummyRequest
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest

from .base import BaseTestCase


class WebSoscketHandshake(BaseTestCase):

    def test_websocket_upgrade(self):
        from pyramid_sockjs.websocket import init_websocket, HandshakeError
        request = DummyRequest()

        self.assertRaises(HandshakeError, init_websocket, request)

        request.environ['HTTP_UPGRADE'] = 'ssl'
        self.assertRaises(HandshakeError, init_websocket, request)

    def test_connection_upgrade(self):
        from pyramid_sockjs.websocket import init_websocket, HandshakeError
        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'close'})

        err = None
        try:
            init_websocket(request)
        except Exception as err:
            pass

        self.assertIsInstance(err, HandshakeError)
        self.assertEqual(str(err), 'Connection does not support upgrade.')

    def test_websocket_version(self):
        from pyramid_sockjs.websocket import init_websocket, HandshakeError

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade'})

        err = None
        try:
            init_websocket(request)
        except Exception as err:
            pass

        self.assertIsInstance(err, HandshakeError)
        self.assertEqual(err.msg, 'Unsupported WebSocket version.')

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '5'})

        err = None
        try:
            init_websocket(request)
        except Exception as err:
            pass

        self.assertIsInstance(err, HandshakeError)
        self.assertEqual(err.msg, 'Unsupported WebSocket version.')

    def test_method_type(self):
        from pyramid_sockjs.websocket import init_websocket, HandshakeError

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8'})
        request.method = 'POST'

        err = None
        try:
            init_websocket(request)
        except Exception as err:
            pass

        self.assertIsInstance(err, HandshakeError)
        self.assertEqual(err.msg, 'Method is not GET')

    def test_protocol_type(self):
        from pyramid_sockjs.websocket import init_websocket, HandshakeError

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTPS/1.1'})
        request.method = 'GET'

        err = None
        try:
            init_websocket(request)
        except Exception as err:
            pass

        self.assertIsInstance(err, HandshakeError)
        self.assertEqual(err.msg, 'Protocol is not HTTP')

    def test_protocol_version(self):
        from pyramid_sockjs.websocket import init_websocket, HandshakeError

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTP/1.0'})
        request.method = 'GET'

        err = None
        try:
            init_websocket(request)
        except Exception as err:
            pass

        self.assertIsInstance(err, HandshakeError)
        self.assertEqual(err.msg, 'HTTP/1.1 is required')

    def test_websocket_key(self):
        from pyramid_sockjs.websocket import init_websocket, HandshakeError

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTP/1.1',
                     'HTTP_SEC_WEBSOCKET_KEY': None,})
        request.method = 'GET'

        err = None
        try:
            init_websocket(request)
        except Exception as err:
            pass

        self.assertIsInstance(err, HandshakeError)
        self.assertEqual(err.msg, 'HTTP_SEC_WEBSOCKET_KEY is invalid key')

    def test_gevent_wsgi_input(self):
        from pyramid_sockjs.websocket import init_websocket, HandshakeError

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTP/1.1',
                     'HTTP_SEC_WEBSOCKET_KEY': '5Jfbk3Hf5oLcReU416OxpA==',
                     'wsgi.input': object()})
        request.method = 'GET'

        err = None
        try:
            init_websocket(request)
        except Exception as err:
            pass

        self.assertIsInstance(err, HandshakeError)
        self.assertTrue(err.msg.startswith("Can't find rfile from"))

    def test_success(self):
        from pyramid_sockjs.websocket import init_websocket, HandshakeError

        class Input(object):
            rfile = object()

        class WS(object):
            def __init__(self, rfile, environ):
                self.rfile = rfile
                self.environ = environ

        request = DummyRequest(
            environ={'HTTP_UPGRADE': 'websocket',
                     'HTTP_CONNECTION': 'keep-alive, upgrade',
                     'HTTP_SEC_WEBSOCKET_VERSION': '8',
                     'SERVER_PROTOCOL': 'HTTP/1.1',
                     'HTTP_SEC_WEBSOCKET_KEY': '5Jfbk3Hf5oLcReU416OxpA==',
                     'wsgi.input': Input()})
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
        self.assertEqual(response.headers['Sec-WebSocket-Version'], 'hybi-8')
