""" iframe-htmlfile transport """
import asyncio
import re

from aiohttp import web
from sockjs.protocol import close_frame, dumps
from sockjs.protocol import ENCODING, STATE_CLOSING, FRAME_CLOSE
from sockjs.exceptions import SessionIsAcquired

from .base import StreamingTransport
from .utils import session_cookie, cors_headers


PRELUDE1 = b"""
<!doctype html>
<html><head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head><body><h2>Don't panic!</h2>
  <script>
    document.domain = document.domain;
    var c = parent."""

PRELUDE2 = b""";
    c.start();
    function p(d) {c.message(d);};
    window.onload = function() {c.stop();};
  </script>"""


class HTMLFileTransport(StreamingTransport):

    maxsize = 131072  # 128K bytes
    check_callback = re.compile('^[a-zA-Z0-9_\.]+$')

    @asyncio.coroutine
    def send_text(self, text):
        blob = (
            '<script>\np(%s);\n</script>\r\n' % dumps(text)).encode(ENCODING)
        yield from self.response.write(blob)

        self.size += len(blob)
        if self.size > self.maxsize:
            yield from self.manager.release(self.session)
            self.waiter.set_result(True)

    def process(self):
        session = self.session
        request = self.request

        headers = list(
            (('Content-Type', 'text/html; charset=UTF-8'),
             ('Cache-Control',
              'no-store, no-cache, must-revalidate, max-age=0'),
             ("Connection", "close")) +
            session_cookie(request) +
            cors_headers(request.headers))

        callback = request.GET.get('c', None)
        if callback is None:
            yield from self.session._remote_closed()
            return web.HTTPBadRequest(body=b'"callback" parameter required')

        elif not self.check_callback.match(callback):
            yield from self.session._remote_closed()
            return web.HTTPBadRequest(body=b'invalid "callback" parameter')

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=headers)
        resp.start(self.request)
        resp.write(b''.join(
            (PRELUDE1, callback.encode('utf-8'), PRELUDE2, b' '*1024)))

        # session was interrupted
        if session.interrupted:
            self.send_blob(close_frame(1002, b"Connection interrupted"))

        # session is closed
        elif session.state == STATE_CLOSING:
            yield from self.session._remote_closed()
            self.send_blob(close_frame(3000, b'Go away!'))

        else:
            # acquire session
            try:
                yield from self.manager.acquire(self.session, self)
            except SessionIsAcquired:
                yield from self.send_blob(
                    close_frame(2010, b"Another connection still open"))
            else:
                yield from self.waiter

        return resp
