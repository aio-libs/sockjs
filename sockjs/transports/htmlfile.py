"""iframe-htmlfile transport"""

import re

from aiohttp import hdrs, web
from multidict import MultiDict

from .base import StreamingTransport
from .utils import CACHE_CONTROL, session_cookie
from ..protocol import dumps


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
    name = "htmlfile"
    create_session = True
    check_callback = re.compile(r"^[a-zA-Z0-9_\.]+$")

    async def _send(self, text: str):
        text = "<script>\np(%s);\n</script>\r\n" % dumps(text)
        return await super()._send(text)

    async def process(self):
        request = self.request

        callback = request.query.get("c")
        if callback is None:
            await self.manager.remote_closed(self.session)
            raise web.HTTPInternalServerError(text='"callback" parameter required')

        elif not self.check_callback.match(callback):
            await self.manager.remote_closed(self.session)
            raise web.HTTPInternalServerError(text='invalid "callback" parameter')

        headers = (
            (hdrs.CONTENT_TYPE, "text/html; charset=UTF-8"),
            (hdrs.CACHE_CONTROL, CACHE_CONTROL),
            (hdrs.CONNECTION, "close"),
        )
        headers += session_cookie(request)

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=MultiDict(headers))
        await resp.prepare(self.request)
        await resp.write(
            b"".join((PRELUDE1, callback.encode("utf-8"), PRELUDE2, b" " * 1024))
        )

        # handle session
        await self.handle_session()

        return resp
