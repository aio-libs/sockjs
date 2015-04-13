import asyncio
from aiohttp import web, hdrs, errors

from .base import StreamingTransport
from .utils import session_cookie, cors_headers, cache_headers
from ..exceptions import SessionIsAcquired
from ..protocol import close_frame, ENCODING, STATE_CLOSING, STATE_CLOSED


class XHRStreamingTransport(StreamingTransport):

    maxsize = 131072  # 128K bytes
    open_seq = b'h' * 2048 + b'\n'

    def process(self):
        request = self.request
        headers = list(
            ((hdrs.CONNECTION, request.headers.get(hdrs.CONNECTION, 'close')),
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
            msg = '%s\n' % close_frame(1002, "Connection interrupted")
            resp.write(msg.encode(ENCODING))

        # session is closing
        elif self.session.state == STATE_CLOSING:
            yield from self.session._remote_closed()
            msg = '%s\n' % close_frame(3000, 'Go away!')
            resp.write(msg.encode(ENCODING))

        # session is closed
        elif self.session.state == STATE_CLOSED:
            msg = '%s\n' % close_frame(3000, 'Go away!')
            resp.write(msg.encode(ENCODING))

        else:
            # acquire session
            try:
                yield from self.manager.acquire(self.session, self)
            except SessionIsAcquired:
                msg = '%s\n' % close_frame(
                    2010, "Another connection still open")
                resp.write(msg.encode(ENCODING))
            else:
                try:
                    yield from self.waiter
                except asyncio.CancelledError:
                    yield from self.session._remote_close(
                        exc=errors.ClientDisconnectedError)
                    yield from self.session._remote_closed()
                    raise

        return resp
