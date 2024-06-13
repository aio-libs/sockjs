from aiohttp import hdrs, web
from multidict import MultiDict

from .base import StreamingTransport
from .utils import CACHE_CONTROL, cache_headers, session_cookie


class XHRStreamingTransport(StreamingTransport):
    name = "xhr-streaming"
    create_session = True
    open_seq = b"h" * 2048 + b"\n"

    async def _send(self, text: str):
        return await super()._send(text + "\n")

    async def process(self):
        request = self.request
        headers = (
            (hdrs.CONNECTION, request.headers.get(hdrs.CONNECTION, "close")),
            (hdrs.CONTENT_TYPE, "application/javascript; charset=UTF-8"),
            (hdrs.CACHE_CONTROL, CACHE_CONTROL),
        )

        headers += session_cookie(request)

        if request.method == hdrs.METH_OPTIONS:
            headers += ((hdrs.ACCESS_CONTROL_ALLOW_METHODS, "OPTIONS, POST"),)
            headers += cache_headers()
            return web.Response(status=204, headers=MultiDict(headers))

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=MultiDict(headers))
        resp.force_close()
        await resp.prepare(request)
        await resp.write(self.open_seq)

        # event loop
        await self.handle_session()

        return resp
