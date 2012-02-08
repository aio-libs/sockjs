import base64
from hashlib import sha1
from socket import SHUT_RDWR
from pyramid.httpexceptions import HTTPBadRequest, HTTPMethodNotAllowed
from geventwebsocket.websocket import WebSocketHybi

KEY = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SUPPORTED_VERSIONS = ('13', '8', '7')


class WebSocketHybi(WebSocketHybi):

    def _close(self):
        if self.socket is not None:
            self.socket.shutdown(SHUT_RDWR)
            self.socket = None
            self._write = None

            if not self._reading:
                self.fobj.close()

            self.fobj = None


def init_websocket(request):
    environ = request.environ

    if request.method != "GET":
        request.response.status = 405
        request.response.headers = (('Allow','GET'),)
        return request.response

    if 'websocket' not in environ.get('HTTP_UPGRADE', '').lower():
        return HTTPBadRequest('Can "Upgrade" only to "WebSocket".')

    if 'upgrade' not in environ.get('HTTP_CONNECTION', '').lower():
        return HTTPBadRequest('"Connection" must be "Upgrade".')

    version = environ.get("HTTP_SEC_WEBSOCKET_VERSION")
    if not version or version not in SUPPORTED_VERSIONS:
        return HTTPBadRequest('Unsupported WebSocket version.')

    environ['wsgi.websocket_version'] = 'hybi-%s' % version

    # check client handshake for validity
    protocol = environ.get('SERVER_PROTOCOL','')
    if not protocol.startswith("HTTP/"):
        return HTTPBadRequest('Protocol is not HTTP')

    if not (environ.get('GATEWAY_INTERFACE','').endswith('/1.1') or \
              protocol.endswith('/1.1')):
        return HTTPBadRequest('HTTP/1.1 is required')

    key = environ.get("HTTP_SEC_WEBSOCKET_KEY")
    if not key or len(base64.b64decode(key)) != 16:
        return HTTPBadRequest('HTTP_SEC_WEBSOCKET_KEY is invalid key')

    # get gevent.socket see pyramid_sockjs.monkey
    socket = environ.get('gunicorn.socket', None)
    if socket is None:
        return HTTPBadRequest("socket object is not available")

    headers = [
        ("Upgrade", "websocket"),
        ("Connection", "Upgrade"),
        ("Sec-WebSocket-Accept", base64.b64encode(sha1(key + KEY).digest()))]
    request.response.headers = headers
    request.response.status = '101 Switching Protocols'

    environ['wsgi.websocket'] = WebSocketHybi(socket, environ)
