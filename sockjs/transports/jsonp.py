"""jsonp transport"""
import asyncio
import re
from urllib.parse import unquote_plus

from aiohttp import web, hdrs

from sockjs.protocol import FRAME_OPEN, FRAME_CLOSE, STATE_CLOSING
from sockjs.protocol import encode, decode, close_frame, messages_frame
from sockjs.exceptions import SessionIsAcquired

from .base import Transport
from .utils import session_cookie, cors_headers


class JSONPolling(Transport):

    timing = 5.0
    check_callback = re.compile('^[a-zA-Z0-9_\.]+$')

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
        session = self.session
        request = self.request
        meth = request.method

        if request.method == hdrs.METH_GET:

            callback = request.GET.get('c')
            if not callback:
                yield from self.session._remote_closed()
                return web.HTTPBadRequest(body=b'"callback" parameter required')

            elif not self.check_callback.match(callback):
                yield from self.session._remote_closed()
                return web.HTTPBadRequest(body=b'invalid "callback" parameter')

            if session.state == STATE_CLOSING:
                message = close_frame(3000, b'Go away!')
                body = b''.join((
                    callback.encode('utf-8'),
                    b'(', encode(message), b');\r\n'))

                return web.Response(
                    body=body,
                    content_type='application/javascript; charset=UTF-8',
                    headers=(
                        (hdrs.CACHE_CONTROL,
                         'no-store, no-cache, must-revalidate, max-age=0'),))

            # session was interrupted
            if session.interrupted:
                message = close_frame(1002, b"Connection interrupted")

            # session closed
            elif session.state == STATE_CLOSING:
                yield from session._remote_closed()
                message = close_frame(3000, b'Go away!')

            else:
                try:
                    yield from self.manager.acquire(session, self)
                except SessionIsAcquired:
                    message = close_frame(
                        2010, b"Another connection still open")
                else:
                    try:
                        message = yield from asyncio.wait_for(
                            self.waiter, timeout=self.timing, loop=self.loop)
                    except TimeoutError:
                        message = b'a[]'

                headers = list(
                    ((hdrs.CONTENT_TYPE,
                      'application/javascript; charset=UTF-8'),
                     (hdrs.CACHE_CONTROL,
                      'no-store, no-cache, must-revalidate, max-age=0')) +
                    session_cookie(request) +
                    cors_headers(request.headers))

                body = b''.join((
                    callback.encode('utf-8'), b'(', encode(message), b');\r\n'))
                return web.Response(headers=headers, body=body)

        elif request.method == hdrs.METH_POST:
            data = yield from request.read()

            ctype = request.headers.get(hdrs.CONTENT_TYPE, '').lower()
            if ctype == 'application/x-www-form-urlencoded':
                if not data.startswith(b'd='):
                    return web.HTTPBadRequest(body=b"Payload expected.")

                data = unquote_plus(data[2:].decode('utf-8'))

            if not data:
                return web.HTTPBadRequest(body=b"Payload expected.")

            try:
                messages = decode(data)
            except:
                return web.HTTPBadRequest(body=b'Broken JSON encoding.')

            yield from session._remote_messages(messages)
            return web.Response(
                body=b'ok',
                headers=((hdrs.CONTENT_TYPE,
                          'text/plain; charset=UTF-8'),
                         (hdrs.CACHE_CONTROL,
                          'no-store, no-cache, must-revalidate, max-age=0')) +
                         session_cookie(request))

        else:
            return web.HTTPBadRequest("No support for such method: %s" % meth)
