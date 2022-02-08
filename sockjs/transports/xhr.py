from aiohttp import hdrs, web

from .base import StreamingTransport
from .utils import CACHE_CONTROL, cache_headers, cors_headers, session_cookie


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
            headers += cors_headers(request.headers)
            headers += cache_headers()
            return web.Response(status=204, headers=headers)

        headers = (
            (hdrs.CONTENT_TYPE, "application/javascript; charset=UTF-8"),
            (hdrs.CACHE_CONTROL, CACHE_CONTROL),
        )
        headers += session_cookie(request)
        headers += cors_headers(request.headers)

        resp = self.response = web.StreamResponse(headers=headers)
        await resp.prepare(request)

        await self.handle_session()
        return resp
