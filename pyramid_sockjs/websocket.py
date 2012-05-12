import re
import base64
import struct
from hashlib import md5, sha1
from socket import SHUT_RDWR
from pyramid.httpexceptions import HTTPBadRequest, HTTPMethodNotAllowed
from geventwebsocket.handler import reconstruct_url
from geventwebsocket.websocket import WebSocketHybi, WebSocketHixie

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


class WebSocketHixie(WebSocketHixie):

    def __init__(self, socket, environ):
        super(WebSocketHixie, self).__init__(socket, environ)

        self.socket = socket

    def close(self, message=''):
        if self.socket is not None:
            self.socket.shutdown(SHUT_RDWR)
            self.socket = None
            self._write = None
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

    # get socket object
    socket = environ.get('gunicorn.socket', None)
    if socket is None:
        socket = environ.get('gevent.socket', None)
        if socket is None:
            return HTTPBadRequest("socket object is not available")
        environ['gunicorn.socket'] = socket

    headers = [
        ("Upgrade", "websocket"),
        ("Connection", "Upgrade"),
        ("Sec-WebSocket-Accept", base64.b64encode(sha1(key + KEY).digest()))]
    request.response.headers = headers
    request.response.status = '101 Switching Protocols'

    environ['wsgi.websocket'] = WebSocketHybi(socket, environ)


def get_key_value(key_value):
    key_number = int(re.sub("\\D", "", key_value))
    spaces = re.subn(" ", "", key_value)[1]

    if key_number % spaces != 0:
        raise Exception(
            "key_number %d is not an intergral multiple of spaces %d",
            key_number, spaces)
    else:
        return key_number / spaces


def init_websocket_hixie(request):
    environ = request.environ

    socket = environ.get('gunicorn.socket', None)
    if socket is None:
        socket = environ.get('gevent.socket', None)
        if socket is None:
            return HTTPBadRequest("socket object is not available")
        environ['gunicorn.socket'] = socket

    websocket = WebSocketHixie(socket, environ)
    environ['wsgi.websocket'] = websocket

    key1 = environ.get('HTTP_SEC_WEBSOCKET_KEY1')
    key2 = environ.get('HTTP_SEC_WEBSOCKET_KEY2')

    if key1 is not None:
        environ['wsgi.websocket_version'] = 'hixie-76'
        if not key1:
            return HTTPBadRequest('SEC-WEBSOCKET-KEY1 header is empty')
        if not key2:
            return HTTPBadRequest('SEC-WEBSOCKET-KEY2 header is empty')

        try:
            part1 = get_key_value(key1)
            part2 = get_key_value(key2)
            environ['wsgi.hixie-keys'] = (part1, part2, socket)
        except Exception as err:
            return HTTPBadRequest(str(err))

        headers = [
            ("Upgrade", "WebSocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Location", reconstruct_url(environ)),
            ]
        if websocket.protocol is not None:
            headers.append(("Sec-WebSocket-Protocol", websocket.protocol))

        if websocket.origin:
            headers.append(("Sec-WebSocket-Origin", websocket.origin))

        request.response.headers = headers
        request.response.status = '101 Switching Protocols Handshake'
    else:
        environ['wsgi.websocket_version'] = 'hixie-75'
        headers = [
            ("Upgrade", "WebSocket"),
            ("Connection", "Upgrade"),
            ("WebSocket-Location", reconstruct_url(environ)),
            ]

        if websocket.protocol is not None:
            headers.append(("WebSocket-Protocol", websocket.protocol))
        if websocket.origin:
            headers.append(("WebSocket-Origin", websocket.origin))

        request.response.headers = headers
        request.response.status = '101 Switching Protocols Handshake'
