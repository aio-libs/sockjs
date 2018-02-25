from aiohttp import web, hdrs

from .base import StreamingTransport
from .utils import CACHE_CONTROL, session_cookie, cors_headers, cache_headers


class XHRStreamingTransport(StreamingTransport):

    maxsize = 131072  # 128K bytes
    open_seq = b'h' * 2048 + b'\n'

    async def process(self):
        request = self.request
        headers = list(
            ((hdrs.CONNECTION, request.headers.get(hdrs.CONNECTION, 'close')),
             (hdrs.CONTENT_TYPE,
              'application/javascript; charset=UTF-8'),
             (hdrs.CACHE_CONTROL, CACHE_CONTROL)) +
            session_cookie(request) + cors_headers(request.headers)
        )

        if request.method == hdrs.METH_OPTIONS:
            headers.append(
                (hdrs.ACCESS_CONTROL_ALLOW_METHODS, 'OPTIONS, POST'))
            headers.extend(cache_headers())
            return web.Response(status=204, headers=headers)

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=headers)
        resp.force_close()
        await resp.prepare(request)
        await resp.write(self.open_seq)

        # event loop
        await self.handle_session()

        return resp
