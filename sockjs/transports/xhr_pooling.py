from aiohttp import hdrs, web
from multidict import MultiDict

from .base import StreamingTransport, Transport
from .utils import CACHE_CONTROL, cache_headers, session_cookie
from ..protocol import loads, ENCODING


class XHRTransport(StreamingTransport):
    """Long polling derivative transports,
    used for XHRPolling and JSONPolling."""

    name = "xhr-polling"
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


class XHRSendTransport(Transport):
    name = "xhr-polling"
    create_session = False

    async def process(self):
        request = self.request

        if request.method not in (hdrs.METH_GET, hdrs.METH_POST, hdrs.METH_OPTIONS):
            raise web.HTTPForbidden(text="Method is not allowed")

        if self.request.method == hdrs.METH_OPTIONS:
            headers = (
                (hdrs.ACCESS_CONTROL_ALLOW_METHODS, "OPTIONS, POST"),
                (hdrs.CONTENT_TYPE, "application/javascript; charset=UTF-8"),
            )
            headers += session_cookie(request)
            headers += cache_headers()
            return web.Response(status=204, headers=MultiDict(headers))

        data = await request.read()
        if not data:
            raise web.HTTPInternalServerError(text="Payload expected.")

        try:
            messages = loads(data.decode(ENCODING))
        except Exception:
            raise web.HTTPInternalServerError(text="Broken JSON encoding.")

        await self.manager.remote_messages(self.session, messages)

        headers = (
            (hdrs.CONTENT_TYPE, "text/plain; charset=UTF-8"),
            (hdrs.CACHE_CONTROL, CACHE_CONTROL),
        )
        headers += session_cookie(request)

        return web.Response(status=204, headers=MultiDict(headers))
