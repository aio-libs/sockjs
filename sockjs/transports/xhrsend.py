from aiohttp import hdrs, web
from multidict import MultiDict

from .base import Transport
from .utils import CACHE_CONTROL, cache_headers, session_cookie
from ..protocol import ENCODING, loads


class XHRSendTransport(Transport):
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

        await self.session._remote_messages(messages)

        headers = (
            (hdrs.CONTENT_TYPE, "text/plain; charset=UTF-8"),
            (hdrs.CACHE_CONTROL, CACHE_CONTROL),
        )
        headers += session_cookie(request)

        return web.Response(status=204, headers=MultiDict(headers))
