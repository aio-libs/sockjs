from aiohttp import web, hdrs

from ..protocol import loads, ENCODING
from .base import Transport
from .utils import CACHE_CONTROL, session_cookie, cors_headers, cache_headers


class XHRSendTransport(Transport):

    async def process(self):
        request = self.request

        if request.method not in (
                hdrs.METH_GET, hdrs.METH_POST, hdrs.METH_OPTIONS):
            return web.HTTPForbidden(text='Method is not allowed')

        if self.request.method == hdrs.METH_OPTIONS:
            base_headers = (
                (hdrs.ACCESS_CONTROL_ALLOW_METHODS, 'OPTIONS, POST'),
                (hdrs.CONTENT_TYPE, 'application/javascript; charset=UTF-8'))
            headers = list(
                base_headers +
                session_cookie(request) +
                cors_headers(request.headers) +
                cache_headers())
            return web.Response(status=204, headers=headers)

        data = await request.read()
        if not data:
            return web.HTTPInternalServerError(text='Payload expected.')

        try:
            messages = loads(data.decode(ENCODING))
        except Exception:
            return web.HTTPInternalServerError(text="Broken JSON encoding.")

        await self.session._remote_messages(messages)

        headers = list(
            ((hdrs.CONTENT_TYPE, 'text/plain; charset=UTF-8'),
             (hdrs.CACHE_CONTROL, CACHE_CONTROL)) +
            session_cookie(request) +
            cors_headers(request.headers))

        return web.Response(status=204, headers=headers)
