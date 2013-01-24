import base64
import hashlib
import re
import struct
import tulip
from hashlib import md5
from urllib.parse import quote
from pyramid.httpexceptions import HTTPBadRequest, HTTPMethodNotAllowed
from pyramid_sockjs.exceptions import WebSocketError, FrameTooLargeException


KEY = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SUPPORTED_VERSIONS = ('13', '8', '7')


def init_websocket(request):
    environ = request.environ

    if request.method != "GET":
        raise HTTPMethodNotAllowed(headers=(('Allow','GET'),), empty_body=True)

    if 'websocket' not in environ.get('HTTP_UPGRADE', '').lower():
        raise HTTPBadRequest('Can "Upgrade" only to "WebSocket".')

    if 'upgrade' not in environ.get('HTTP_CONNECTION', '').lower():
        raise HTTPBadRequest('"Connection" must be "Upgrade".')

    version = environ.get("HTTP_SEC_WEBSOCKET_VERSION")
    if not version or version not in SUPPORTED_VERSIONS:
        raise HTTPBadRequest('Unsupported WebSocket version.')

    environ['wsgi.websocket_version'] = 'hybi-%s' % version

    # check client handshake for validity
    protocol = environ.get('SERVER_PROTOCOL','')
    if not protocol.startswith("HTTP/"):
        raise HTTPBadRequest('Protocol is not HTTP')

    if not (environ.get('GATEWAY_INTERFACE','').endswith('/1.1') or \
              protocol.endswith('/1.1')):
        raise HTTPBadRequest('HTTP/1.1 is required')

    key = environ.get("HTTP_SEC_WEBSOCKET_KEY")
    if not key or len(base64.b64decode(key)) != 16:
        raise HTTPBadRequest('HTTP_SEC_WEBSOCKET_KEY is invalid key')

    # prepare response
    return ('101 Switching Protocols', 
            [("Upgrade", "websocket"),
             ("Connection", "Upgrade"),
             ("Transfer-Encoding", "chunked"),
             ("Sec-WebSocket-Accept", base64.b64encode(
                 hashlib.sha1((key + KEY).encode()).digest()).decode())],
            WebSocketHybi(
                request.environ['tulip.read'],
                request.environ['tulip.write'],
                request.environ))


class WebSocketHybi:
    OPCODE_TEXT = 0x1
    OPCODE_BINARY = 0x2
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    def __init__(self, read, write, environ):
        self.environ = environ
        self._chunks = bytearray()

        self._read = read
        self._write = write

        self.close_code = None
        self.close_message = None
        self._reading = False
        self._closed = False

    def _parse_header(self, data):
        if len(data) != 2:
            raise WebSocketError(
                'Incomplete read while reading header: %r' % data)

        first_byte, second_byte = struct.unpack('!BB', data)

        fin = (first_byte >> 7) & 1
        rsv1 = (first_byte >> 6) & 1
        rsv2 = (first_byte >> 5) & 1
        rsv3 = (first_byte >> 4) & 1
        opcode = first_byte & 0xf

        # frame-fin = %x0 ; more frames of this message follow
        #           / %x1 ; final frame of this message

        # frame-rsv1 = %x0 ; 1 bit, MUST be 0 unless negotiated otherwise
        # frame-rsv2 = %x0 ; 1 bit, MUST be 0 unless negotiated otherwise
        # frame-rsv3 = %x0 ; 1 bit, MUST be 0 unless negotiated otherwise
        if rsv1 or rsv2 or rsv3:
            self.close(1002)
            raise WebSocketError(
                'Received frame with non-zero reserved bits: %r' % str(data))

        if opcode > 0x7 and fin == 0:
            self.close(1002)
            raise WebSocketError(
                'Received fragmented control frame: %r' % str(data))

        if len(self._chunks) > 0 and fin == 0 and not opcode:
            self.close(1002)
            raise WebSocketError(
                'Received new fragment frame with non-zero opcode: %r' % 
                str(data))

        if (len(self._chunks) > 0 and fin == 1 and 
            (self.OPCODE_TEXT <= opcode <= self.OPCODE_BINARY)):
            self.close(1002)
            raise WebSocketError(
                'Received new unfragmented data frame during '
                'fragmented message: %r' % str(data))

        has_mask = (second_byte >> 7) & 1
        length = (second_byte) & 0x7f

        # Control frames MUST have a payload length of 125 bytes or less
        if opcode > 0x7 and length > 125:
            self.close(1002)
            raise FrameTooLargeException(
                "Control frame payload cannot be larger than 125 "
                "bytes: %r" % str(data))

        return fin, opcode, has_mask, length

    def _receive_frame(self):
        """Return the next frame from the socket."""
        read = self._read

        data0 = yield from read(2)
        if not data0:
            return

        fin, opcode, has_mask, length = self._parse_header(data0)

        if not has_mask and length:
            self.close(1002)
            raise WebSocketError('Message from client is not masked')

        if length < 126:
            data1 = b''
        elif length == 126:
            data1 = yield from read(2)

            if len(data1) != 2:
                self.close()
                raise WebSocketError(
                    'Incomplete read while reading 2-byte length: %r' % (
                        data0 + data1))

            length = struct.unpack('!H', data1)[0]
        else:
            data1 = yield from read(8)

            if len(data1) != 8:
                self.close()
                raise WebSocketError(
                    'Incomplete read while reading 8-byte length: %r' % (
                        data0 + data1))

            length = struct.unpack('!Q', data1)[0]

        if has_mask:
            mask = yield from read(4)
            if len(mask) != 4:
                raise WebSocketError(
                    'Incomplete read while reading mask: %r' % (
                        data0 + data1 + mask))

            mask = struct.unpack('!BBBB', mask)

        if length:
            payload = yield from read(length)
            if len(payload) != length:
                args = (length, len(payload))
                raise WebSocketError(
                    'Incomplete read: expected message of %s bytes, '
                    'got %s bytes' % args)
        else:
            payload = b''

        if payload:
            payload = bytearray(payload)
            
            for i in range(len(payload)):
                payload[i] = payload[i] ^ mask[i % 4]

        return fin, opcode, payload

    def _receive(self):
        """Return the next text or binary message from the socket."""
        opcode = None
        result = bytearray()

        while True:
            try:
                frame = yield from self._receive_frame()
            except:
                if self._closed:
                    return
                raise
            if frame is None:
                if result:
                    raise WebSocketError('Peer closed connection unexpectedly')
                return

            f_fin, f_opcode, f_payload = frame

            if f_opcode in (self.OPCODE_TEXT, self.OPCODE_BINARY):
                if opcode is None:
                    opcode = f_opcode
                else:
                    raise WebSocketError(
                        'The opcode in non-fin frame is expected '
                        'to be zero, got %r' % (f_opcode, ))

            elif not f_opcode:
                if opcode is None:
                    self.close(1002)
                    raise WebSocketError('Unexpected frame with opcode=0')

            elif f_opcode == self.OPCODE_CLOSE:
                if len(f_payload) >= 2:
                    self.close_code = struct.unpack('!H', str(f_payload[:2]))[0]
                    self.close_message = f_payload[2:]
                elif f_payload:
                    raise WebSocketError(
                        'Invalid close frame: %s %s %s' % (
                            f_fin, f_opcode, repr(f_payload)))

                code = self.close_code
                if code is None or (code >= 1000 and code < 5000):
                    self.close()
                else:
                    self.close(1002)
                    raise WebSocketError(
                        'Received invalid close frame: %r %r' % (
                            code, self.close_message))
                return

            elif f_opcode == self.OPCODE_PING:
                self._send_frame(f_payload, opcode=self.OPCODE_PONG)
                continue

            elif f_opcode == self.OPCODE_PONG:
                continue

            else:
                raise WebSocketError("Unexpected opcode=%r" % (f_opcode, ))

            result.extend(f_payload)
            if f_fin:
                break

        if opcode == self.OPCODE_TEXT:
            return result, False
        elif opcode == self.OPCODE_BINARY:
            return result, True
        else:
            raise AssertionError(
                'internal serror in websocket: opcode=%r' % (opcode, ))

    @tulip.coroutine
    def receive(self):
        result = yield from self._receive()
        if not result:
            return

        message, is_binary = result
        if is_binary:
            return message
        else:
            try:
                return message.decode('utf-8')
            except ValueError:
                self.close(1007)
                raise

    def _send_frame(self, message, opcode):
        """Send a frame over the websocket with message as its payload"""
        header = bytes([0x80 | opcode])
        msg_length = len(message)

        if msg_length < 126:
            header += bytes([msg_length])
        elif msg_length < (1 << 16):
            header += bytes([126]) + struct.pack('!H', msg_length)
        elif msg_length < (1 << 63):
            header += bytes([127]) + struct.pack('!Q', msg_length)
        else:
            raise FrameTooLargeException()

        self._write(header + message)

    def send(self, message, binary=False):
        """Send a frame over the websocket with message as its payload"""
        if binary:
            return self._send_frame(message, self.OPCODE_BINARY)
        else:
            return self._send_frame(message, self.OPCODE_TEXT)

    def close(self, code=1000, message=b''):
        """Close the websocket, sending the specified code and message"""
        if not self._closed:
            self._send_frame(
                struct.pack('!H%ds' % len(message), code, message),
                opcode=self.OPCODE_CLOSE)
            self._closed = True


def reconstruct_url(environ):
    secure = environ['wsgi.url_scheme'] == 'https'
    if secure:
        url = 'wss://'
    else:
        url = 'ws://'

    if environ.get('HTTP_HOST'):
        url += environ['HTTP_HOST']
    else:
        url += environ['SERVER_NAME']

        if secure:
            if environ['SERVER_PORT'] != '443':
                url += ':' + environ['SERVER_PORT']
        else:
            if environ['SERVER_PORT'] != '80':
                url += ':' + environ['SERVER_PORT']

    url += quote(environ.get('SCRIPT_NAME', ''))
    url += quote(environ.get('PATH_INFO', ''))

    if environ.get('QUERY_STRING'):
        url += '?' + environ['QUERY_STRING']

    return url


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

    read = request.environ['tulip.read']

    websocket = WebSocketHixie(
        read,
        request.environ['tulip.write'],
        request.environ)

    key1 = environ.get('HTTP_SEC_WEBSOCKET_KEY1')
    key2 = environ.get('HTTP_SEC_WEBSOCKET_KEY2')

    if key1 is not None:
        environ['wsgi.websocket_version'] = 'hixie-76'
        if not key1:
            raise HTTPBadRequest('SEC-WEBSOCKET-KEY1 header is empty')
        if not key2:
            raise HTTPBadRequest('SEC-WEBSOCKET-KEY2 header is empty')

        # hixie-76 key
        try:
            part1 = int(get_key_value(key1))
            part2 = int(get_key_value(key2))
            environ['wsgi.hixie_keys'] = (part1, part2)
        except Exception as err:
            raise HTTPBadRequest(str(err))

        # prepare headers
        headers = [
            ("Upgrade", "WebSocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Location", reconstruct_url(environ)),
            ]
        if websocket.protocol is not None:
            headers.append(("Sec-WebSocket-Protocol", websocket.protocol))

        if websocket.origin:
            headers.append(("Sec-WebSocket-Origin", websocket.origin))

        return ('101 Switching Protocols Handshake', headers, websocket)
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

        return ('101 Switching Protocols Handshake', headers, websocket)


class WebSocketHixie:

    def __init__(self, read, write, environ):
        self.origin = environ.get('HTTP_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL')
        self.path = environ.get('PATH_INFO')

        self._read = read
        self._write = write
        self._closed = False

    def send(self, message):
        self._write(b"\x00" + message + b"\xFF")

    def close(self, message=b''):
        if not self._closed:
            self._closed = True
            self._write(b"\xFF")

    def _message_length(self):
        length = 0

        while True:
            byte_str = yield from self._read(1)
            if not byte_str:
                return 0
            else:
                byte = ord(byte_str)

            if byte != 0x00:
                length = length * 128 + (byte & 0x7f)
                if (byte & 0x80) != 0x80:
                    break

        return length

    def _read_until(self):
        bytes = []

        read = self._read

        while True:
            byte = yield from read(1)
            if ord(byte) != 0xff:
                bytes.append(byte)
            else:
                break

        return b''.join(bytes)

    def receive(self):
        read = self._read

        while True:
            frame_str = yield from read(1)

            if not frame_str:
                self.close()
                return
            else:
                frame_type = ord(frame_str)

            if frame_type == 0x00:
                bytes = yield from self._read_until()
                return bytes.decode("utf-8", "replace")
            elif frame_type == 0xff:
                frame_str = yield from read(1)
                frame_type = ord(frame_str)
                if frame_type == 0x00:
                    self._write(b'\xff\x00')
                    return

            raise WebSocketError(
                "Received an invalid frame_type=%r" % frame_type)
