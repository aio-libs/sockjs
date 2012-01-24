import base64
from hashlib import sha1
from geventwebsocket.websocket import WebSocketHybi

KEY = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SUPPORTED_VERSIONS = ('13', '8', '7')


class HandshakeError(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return self.msg


def init_websocket(request):
    environ = request.environ

    if 'websocket' not in environ.get('HTTP_UPGRADE', '').lower():
        raise HandshakeError("Upgrade protocol is not websocket.")

    if 'upgrade' not in environ.get('HTTP_CONNECTION', '').lower():
        raise HandshakeError("Connection does not support upgrade.")

    version = environ.get("HTTP_SEC_WEBSOCKET_VERSION")
    if not version or version not in SUPPORTED_VERSIONS:
        raise HandshakeError('Unsupported WebSocket version.')

    environ['wsgi.websocket_version'] = 'hybi-%s' % version

    # check client handshake for validity
    if request.method != "GET":
        raise HandshakeError('Method is not GET')

    protocol = environ.get('SERVER_PROTOCOL','')
    if not protocol.startswith("HTTP/"):
        raise HandshakeError('Protocol is not HTTP')

    if not (environ.get('GATEWAY_INTERFACE','').endswith('/1.1') or \
              protocol.endswith('/1.1')):
        raise HandshakeError('HTTP/1.1 is required')

    key = environ.get("HTTP_SEC_WEBSOCKET_KEY")
    if not key or len(base64.b64decode(key)) != 16:
        raise HandshakeError('HTTP_SEC_WEBSOCKET_KEY is invalid key')

    # !!!!!!! HACK !!!!!!!
    rfile = getattr(environ['wsgi.input'], 'rfile', None)
    if rfile is None:
        raise HandshakeError("Can't find rfile from %s"%environ['wsgi.input'])
    # !!!!!!! HACK !!!!!!!

    headers = [
        ("Upgrade", "websocket"),
        ("Connection", "Upgrade"),
        ("Content-Length", "0"),
        ('Sec-WebSocket-Version', environ['wsgi.websocket_version']),
        ("Sec-WebSocket-Accept", base64.b64encode(sha1(key + KEY).digest()))]
    request.response.headers = headers
    request.response.status = '101 Switching Protocols'

    environ['wsgi.websocket'] = WebSocketHybi(rfile, environ)
