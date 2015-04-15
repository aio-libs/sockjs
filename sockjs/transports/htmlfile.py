""" iframe-htmlfile transport """
import re
from aiohttp import web, hdrs

from ..protocol import dumps, ENCODING
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

    def send(self, text):
        blob = (
            '<script>\np(%s);\n</script>\r\n' % dumps(text)).encode(ENCODING)
        self.response.write(blob)

        self.size += len(blob)
        if self.size > self.maxsize:
            return True
        else:
            return False

    def process(self):
        request = self.request

        callback = request.GET.get('c', None)
        if callback is None:
            yield from self.session._remote_closed()
            return web.HTTPBadRequest(body=b'"callback" parameter required')

        elif not self.check_callback.match(callback):
            yield from self.session._remote_closed()
            return web.HTTPBadRequest(body=b'invalid "callback" parameter')

        headers = list(
            ((hdrs.CONTENT_TYPE, 'text/html; charset=UTF-8'),
             (hdrs.CACHE_CONTROL,
              'no-store, no-cache, must-revalidate, max-age=0'),
             (hdrs.CONNECTION, 'close')) +
            session_cookie(request) +
            cors_headers(request.headers))

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=headers)
        resp.start(self.request)
        resp.write(b''.join(
            (PRELUDE1, callback.encode('utf-8'), PRELUDE2, b' '*1024)))

        # handle session
        yield from self.handle_session()

        return resp
