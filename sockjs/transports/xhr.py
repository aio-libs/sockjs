from aiohttp import web, hdrs

from .base import StreamingTransport
from .utils import session_cookie, cors_headers, cache_headers


class XHRTransport(StreamingTransport):
    """Long polling derivative transports,
    used for XHRPolling and JSONPolling."""

    timeout = 5.0
    maxsize = 0

    def process(self):
        request = self.request

        if request.method == hdrs.METH_OPTIONS:
            headers = list(
                ((hdrs.CONTENT_TYPE, 'application/javascript; charset=UTF-8'),
                 (hdrs.ACCESS_CONTROL_ALLOW_METHODS, 'OPTIONS, POST')) +
                session_cookie(request) +
                cors_headers(request.headers) +
                cache_headers())
            return web.Response(status=204, headers=headers)

        headers = list(
            ((hdrs.CONTENT_TYPE, 'application/javascript; charset=UTF-8'),
             (hdrs.CACHE_CONTROL,
              'no-store, no-cache, must-revalidate, max-age=0')) +
            session_cookie(request) +
            cors_headers(request.headers))

        resp = self.response = web.StreamResponse(headers=headers)
        resp.start(request)

        yield from self.handle_session()
        return resp
