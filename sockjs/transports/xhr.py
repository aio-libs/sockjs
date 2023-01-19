from aiohttp import hdrs, web
from multidict import MultiDict

from .base import StreamingTransport
from .utils import CACHE_CONTROL, cache_headers, session_cookie


class XHRTransport(StreamingTransport):
    """Long polling derivative transports,
    used for XHRPolling and JSONPolling."""

    create_session = True
    maxsize = 0

    async def _send(self, text: str):
        return await super()._send(text + "\n")

    async def process(self):
        request = self.request

        if request.method == hdrs.METH_OPTIONS:
            headers = (
                (hdrs.CONTENT_TYPE, "application/javascript; charset=UTF-8"),
                (hdrs.ACCESS_CONTROL_ALLOW_METHODS, "OPTIONS, POST"),
            )
            headers += session_cookie(request)
            headers += cache_headers()
            return web.Response(status=204, headers=MultiDict(headers))

        headers = (
            (hdrs.CONTENT_TYPE, "application/javascript; charset=UTF-8"),
            (hdrs.CACHE_CONTROL, CACHE_CONTROL),
        )
        headers += session_cookie(request)

        resp = self.response = web.StreamResponse(headers=MultiDict(headers))
        await resp.prepare(request)

        await self.handle_session()
        return resp
