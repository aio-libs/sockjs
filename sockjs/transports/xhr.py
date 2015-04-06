import asyncio
from itertools import chain
from aiohttp import web, hdrs, errors

from sockjs import STATE_CLOSING, STATE_CLOSED
from sockjs.protocol import FRAME_OPEN, close_frame, messages_frame
from sockjs.exceptions import SessionIsAcquired

from .base import Transport
from .utils import session_cookie, cors_headers, cache_headers


class XHRTransport(Transport):
    """Long polling derivative transports,
    used for XHRPolling and JSONPolling."""

    timing = 5.0

    def __init__(self, manager, session, request):
        super().__init__(manager, session, request)

        self.waiter = asyncio.Future(loop=self.loop)

    def send_open(self):
        self.waiter.set_result(FRAME_OPEN)
        yield from self.manager.release(self.session)
    
    def send_message(self, message):
        self.waiter.set_result(messages_frame(msg))
        yield from self.manager.release(self.session)

    def send_messages(self, messages):
        self.waiter.set_result(messages_frame(messages))
        yield from self.manager.release(self.session)

    def send_message_blob(self, blob):
        self.waiter.set_result(blob)
        yield from self.manager.release(self.session)

    @asyncio.coroutine
    def send_close(self, code, reason):
        self.waiter.set_result(close_frame(code, reason))
        yield from self.session._remote_closed()
        yield from self.manager.release(self.session)

    def process(self):
        request = self.request

        if request.method == hdrs.METH_OPTIONS:
            headers = list(chain(
                ((hdrs.CONTENT_TYPE, 'application/javascript; charset=UTF-8'),
                 (hdrs.ACCESS_CONTROL_ALLOW_METHODS, "OPTIONS, POST")),
                session_cookie(request),
                cors_headers(request.headers),
                cache_headers()))
            return web.Response(status=204, headers=headers)

        session = self.session

        # session was interrupted
        if session.interrupted:
            message = close_frame(1002, b"Connection interrupted") + b'\n'

        # session closed
        elif session.state == STATE_CLOSING:
            yield from session._remote_closed()
            message = close_frame(3000, b'Go away!') + b'\n'

        elif session.state == STATE_CLOSED:
            message = close_frame(3000, b'Go away!') + b'\n'

        else:
            try:
                yield from self.manager.acquire(session, self)
            except SessionIsAcquired:
                message = close_frame(
                    2010, b"Another connection still open") + b'\n'
            else:
                try:
                    message = yield from asyncio.wait_for(
                        self.waiter, timeout=self.timing, loop=self.loop)
                    message += b'\n'
                except TimeoutError:
                    message = b'a[]\n'
                except asyncio.CancelledError:
                    yield from self.session._remote_close(
                        exc=errors.ClientDisconnectedError)
                    yield from self.session._remote_closed()
                    raise

        headers = list(
            ((hdrs.CONTENT_TYPE, 'application/javascript; charset=UTF-8'),
             (hdrs.CACHE_CONTROL,
              'no-store, no-cache, must-revalidate, max-age=0')) +
            session_cookie(request) +
            cors_headers(request.headers))

        return web.Response(headers=headers, body=message)
