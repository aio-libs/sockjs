""" iframe-htmlfile transport """
import re
from aiohttp import web, hdrs

from ..protocol import dumps, ENCODING
from .base import StreamingTransport
from .utils import CACHE_CONTROL, session_cookie, cors_headers


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

    async def send(self, text):
        blob = (
            '<script>\np(%s);\n</script>\r\n' % dumps(text)).encode(ENCODING)
        await self.response.write(blob)

        self.size += len(blob)
        if self.size > self.maxsize:
            return True
        else:
            return False

    async def process(self):
        request = self.request

        try:
            callback = request.query.get('c', None)
        except Exception:
            callback = request.GET.get('c', None)

        if callback is None:
            await self.session._remote_closed()
            return web.HTTPInternalServerError(
                body=b'"callback" parameter required')

        elif not self.check_callback.match(callback):
            await self.session._remote_closed()
            return web.HTTPInternalServerError(
                body=b'invalid "callback" parameter')

        headers = list(
            ((hdrs.CONTENT_TYPE, 'text/html; charset=UTF-8'),
             (hdrs.CACHE_CONTROL, CACHE_CONTROL),
             (hdrs.CONNECTION, 'close')) +
            session_cookie(request) +
            cors_headers(request.headers))

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=headers)
        await resp.prepare(self.request)
        await resp.write(b''.join(
            (PRELUDE1, callback.encode('utf-8'), PRELUDE2, b' '*1024)))

        # handle session
        await self.handle_session()

        return resp
