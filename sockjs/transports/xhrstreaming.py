import asyncio
from aiohttp import web, hdrs, errors
from sockjs.protocol import STATE_CLOSING, STATE_CLOSED
from sockjs.protocol import FRAME_CLOSE, FRAME_OPEN, close_frame, messages_frame
from sockjs.exceptions import SessionIsAcquired

from .base import StreamingTransport
from .utils import session_cookie, cors_headers, cache_headers


class XHRStreamingTransport(StreamingTransport):

    maxsize = 131072  # 128K bytes
    open_seq = b'h' * 2048 + b'\n'

    def process(self):
        request = self.request
        headers = list(
            (#(hdrs.CONNECTION, request.headers.get(hdrs.CONNECTION, 'close')),
             (hdrs.CONNECTION, 'close'),
             (hdrs.CONTENT_TYPE,
              'application/javascript; charset=UTF-8'),
             (hdrs.CACHE_CONTROL,
              'no-store, no-cache, must-revalidate, max-age=0')) +
            session_cookie(request) + cors_headers(request.headers)
        )

        if request.method == hdrs.METH_OPTIONS:
            headers.append(
                (hdrs.ACCESS_CONTROL_ALLOW_METHODS, "OPTIONS, POST"))
            headers.extend(cache_headers())
            return web.Response(status=204, headers=headers)

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=headers)
        resp.start(request)
        resp.write(self.open_seq)

        # session was interrupted
        if self.session.interrupted:
            resp.write(close_frame(1002, b"Connection interrupted") + b'\n')

        # session is closing
        elif self.session.state == STATE_CLOSING:
            yield from self.session._remote_closed()
            resp.write(close_frame(3000, b'Go away!') + b'\n')

        # session is closed
        elif self.session.state == STATE_CLOSED:
            resp.write(close_frame(3000, b'Go away!') + b'\n')

        else:
            # acquire session
            try:
                yield from self.manager.acquire(self.session, self)
            except SessionIsAcquired:
                resp.write(
                    close_frame(2010,
                                b"Another connection still open") + b'\n')
            else:
                try:
                    yield from self.waiter
                except asyncio.CancelledError:
                    yield from self.session._remote_close(
                        exc=errors.ClientDisconnectedError)
                    yield from self.session._remote_closed()
                    raise

        return resp
