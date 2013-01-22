import email
import inspect
import logging
import traceback
import time
import sys
from io import BytesIO
from urllib.parse import unquote

import tulip
from tulip import tasks, futures
from tulip.http_client import StreamReader
from tulip.unix_events import UnixEventLoop

from pprint import pprint

_INTERNAL_ERROR_STATUS = '500 Internal Server Error'
_INTERNAL_ERROR_BODY = b'Internal Server Error'
_INTERNAL_ERROR_HEADERS = [
    (b'Content-Type', b'text/plain'),
    (b'Connection', b'close'),
    (b'Content-Length', bytes(len(_INTERNAL_ERROR_BODY)))]
_WEEKDAYNAME = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHNAME = [None,  # Dummy so we can use 1-based month numbers
              "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def format_date_time(timestamp):
    year, month, day, hh, mm, ss, wd, _y, _z = time.gmtime(timestamp)
    return "%s, %02d %3s %4d %02d:%02d:%02d GMT" % (
        _WEEKDAYNAME[wd], day, _MONTHNAME[month], year, hh, mm, ss)

def bytes_to_str(b):
    if isinstance(b, str):
        return b
    return str(b, 'latin1')


class HTTPProtocol:

    task = None
    chunked = False
    request_version = '1.0'
    headers_sent = False
    close_connection = True
    result = ()

    date = None
    code = 500
    content_length = 0
    status = ''

    base_env = {
        'GATEWAY_INTERFACE': 'CGI/1.1',
        'SERVER_SOFTWARE': 'tulip/wsgi',
        'SCRIPT_NAME': '',
        'wsgi.version': (1, 0),
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
        'wsgi.url_scheme': 'http',
        'wsgi.errors': sys.stderr}

    def __init__(self):
        self._close_callbacks = []

    def connection_made(self, transport):
        self.transport = transport
        self.stream = StreamReader()

    def data_received(self, data):
        if self.task is None:
            self.stream = StreamReader()
            self.task = tasks.Task(self.handle_request())

        self.stream.feed_data(data)

    def eof_received(self):
        self.stream.feed_eof()
        for cb in self._close_callbacks:
            cb()

    def connection_lost(self, exc):
        if self.task and not self.task.done():
            self.task.cancel()

    def add_close_callback(self, cb):
        self._close_callbacks.append(cb)

    @tulip.coroutine
    def handle_request(self):
        status_line = yield from self.stream.readline()

        self.command, self.path, self.request_version = bytes_to_str(
            status_line).split()

        headers = []
        while True:
            header = yield from self.stream.readline()
            if not header.strip():
                break
            headers.append(header)

        parser = email.parser.BytesHeaderParser()
        self.headers = parser.parsebytes(b''.join(headers))
        self.environ = self.get_environ()

        content_length = self.headers.get('content-length')
        if content_length:
            content_length = int(content_length)

            body = yield from self.stream.readexactly(content_length)
            stream = BytesIO(body)
        else:
            stream = BytesIO(b'')

        if self.request_version == "HTTP/1.1":
            conntype = self.headers.get("Connection", "").lower()
            if conntype == "keep-alive":
                self.close_connection = False

        self.environ['wsgi.input'] = stream
        self.environ['tulip.input'] = self.stream
        self.environ['tulip.transport'] = self.transport
        self.environ['tulip.add_close_callback'] = self.add_close_callback
        self.environ['webob.is_body_seekable'] = True

        self.response_headers = []

        try:
            self.result = self.wsgi_app(self.environ, self.start_response)
            if (inspect.isgenerator(self.result) or
                inspect.isgeneratorfunction(self.result)):
                self.result = yield from self.result

            if isinstance(self.result, bytes):
                self.write(self.result)
            else:
                for data in self.result:
                    if isinstance(data, tulip.Future):
                        if not data.done():
                            data = yield from data
                        else:
                            data = data.result()

                    if data is not None:
                        self.write(data)

            if self.status and not self.headers_sent:
                self.write('')

        except:
            traceback.print_exc()
            self.close_conection = True

            self.start_response(_INTERNAL_ERROR_STATUS, _INTERNAL_ERROR_HEADERS)
            self.write(_INTERNAL_ERROR_BODY)

        if self.close_connection:
            self.transport.close()

        self.task.set_result(False)
        self.task = None

        self.chunked = False
        self.request_version = '1.0'
        self.headers_sent = False
        self.close_connection = True
        self.result = ()
        
        self.date = None
        self.code = 500
        self.content_length = 0
        self.status = ''

    def start_response(self, status, headers, exc_info=None):
        self.code = int(status.split(' ', 1)[0])
        self.status = status
        self.response_headers = headers

        connection = None

        self.date = None
        self.content_length = None

        for header, value in headers:
            header = header.lower()
            if header == 'connection':
                connection = value
            elif header == 'date':
                self.date = value
            elif header == 'content-length':
                self.content_length = value
            elif header == 'transfer-encoding' and value == 'chunked':
                self.chunked = True

        if self.request_version == 'HTTP/1.0' and connection is None:
            headers.append(('Connection', 'close'))

        if connection == 'keep-alive':
            self.close_connection = False

        return self.write

    def finalize_headers(self):
        if self.date is None:
            self.response_headers.append(
                ('Date', format_date_time(time.time())))

        if self.code not in (304, 204):
            if self.content_length is None:
                if hasattr(self.result, '__len__'):
                    self.response_headers.append(
                        ('Content-Length',
                         str(sum(len(chunk) for chunk in self.result))))
                else:
                    if self.request_version != 'HTTP/1.0':
                        self.chunked = True
                        self.response_headers.append(
                            ('Transfer-Encoding', 'chunked'))

    def write(self, data):
        if self.headers_sent:
            if self.chunked:
                ## Write the chunked encoding
                data = b''.join(
                    (("%x"%len(data)).encode(), b'\r\n', data, b'\r\n'))
            self.transport.write(data)
        else:
            towrite = []
            self.headers_sent = True
            self.finalize_headers()

            towrite.append(
                ('%s %s\r\n' % (self.request_version, self.status)).encode())
            for header in self.response_headers:
                towrite.append(('%s: %s\r\n' % header).encode())

            towrite.append(b'\r\n')
            if data:
                if self.chunked:
                    ## Write the chunked encoding
                    towrite.append(
                        b''.join(
                            (("%x"%len(data)).encode(), b'\r\n', data, b'\r\n')
                        ))
                else:
                    towrite.append(data)

            self.transport.write(b''.join(towrite))

    def get_environ(self):
        env = dict(self.base_env)
        env['REQUEST_METHOD'] = self.command
        env['SCRIPT_NAME'] = ''

        if '?' in self.path:
            path, query = self.path.split('?', 1)
        else:
            path, query = self.path, ''

        env['PATH_INFO'] = unquote(path)
        env['QUERY_STRING'] = query

        ct = self.headers.get('content-type')
        if ct:
            env['CONTENT_TYPE'] = ct

        length = self.headers.get('content-length')
        if length:
            env['CONTENT_LENGTH'] = int(length)
        env['SERVER_PROTOCOL'] = 'HTTP/1.0'

        #client_address = self.client_address
        #if isinstance(client_address, tuple):
        #    env['REMOTE_ADDR'] = client_address[0]
        #    env['REMOTE_PORT'] = client_address[1]

        for hdr, value in self.headers.items():
            hdr = hdr.replace('-', '_').upper()
            if hdr in (None, 'CONTENT_TYPE', 'CONTENT_LENGTH'):
                continue

            hdr = 'HTTP_' + hdr

            if hdr in env:
                if b'COOKIE' in hdr:
                    env[hdr] += b'; ' + value
                else:
                    env[hdr] += b',' + value
            else:
                env[hdr] = value

        return env


def tulip_server_runner(wsgi_app, global_conf, **kw):
    HTTPProtocol.wsgi_app = wsgi_app

    host = kw.get('host', '0.0.0.0')
    port = int(kw.get('port', '8080'))

    print('Starting Tulip server on http://%s:%s' % (host, port))

    loop = tulip.get_event_loop()
    loop.start_serving(HTTPProtocol, host, port)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    loop.close()
