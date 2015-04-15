from aiohttp import web, hdrs

from ..protocol import loads, ENCODING
from .base import Transport
from .utils import session_cookie, cors_headers, cache_headers


class XHRSendTransport(Transport):

    def process(self):
        request = self.request

        if request.method not in (
                hdrs.METH_GET, hdrs.METH_POST, hdrs.METH_OPTIONS):
            return web.HTTPForbidden(text='Method is not allowed')

        if self.request.method == hdrs.METH_OPTIONS:
            headers = list(
                ((hdrs.ACCESS_CONTROL_ALLOW_METHODS, 'OPTIONS, POST'),
                 (hdrs.CONTENT_TYPE, 'application/javascript; charset=UTF-8'))
                +
                session_cookie(request) +
                cors_headers(request.headers) +
                cache_headers())
            return web.Response(status=204, headers=headers)

        data = yield from request.read()
        if not data:
            return web.HTTPBadRequest(text='Payload expected.')

        try:
            messages = loads(data.decode(ENCODING))
        except:
            return web.HTTPBadRequest(text="Broken JSON encoding.")

        yield from self.session._remote_messages(messages)

        headers = list(
            ((hdrs.CONTENT_TYPE, 'text/plain; charset=UTF-8'),
             (hdrs.CACHE_CONTROL,
              'no-store, no-cache, must-revalidate, max-age=0')) +
            session_cookie(request) +
            cors_headers(request.headers))

        return web.Response(status=204, headers=headers)
