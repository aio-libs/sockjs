import tulip
from itertools import chain
from pyramid_sockjs import STATE_CLOSED
from pyramid_sockjs.protocol import CLOSE, close_frame
from pyramid_sockjs.exceptions import SessionIsAcquired

from .base import Transport
from .utils import session_cookie, cors_headers, cache_headers


class XHRTransport(Transport):
    """Long polling derivative transports,
    used for XHRPolling and JSONPolling."""

    timing = 5.0

    def __call__(self, environ, start_response):
        request = self.request

        if request.method == 'OPTIONS':
            headers = list(chain(
                (('Content-Type', 'application/javascript; charset=UTF-8'),
                 ("Access-Control-Allow-Methods", "OPTIONS, POST")),
                session_cookie(request),
                cors_headers(environ),
                cache_headers()))
            start_response('204 No Content', headers)
            return (b'',)

        session = self.session

        # session was interrupted
        if session.interrupted:
            message = close_frame(1002, b"Connection interrupted")+b'\n'

        # session closed
        elif session.state == STATE_CLOSED:
            message = close_frame(3000, b'Go away!')+b'\n'

        else:
            try:
                session.acquire(request, False)
            except SessionIsAcquired:
                message = close_frame(
                    2010, b"Another connection still open")+b'\n'
            else:
                self.wait = tulip.Task(session.wait())
                tulip.get_event_loop().call_later(
                    self.timing, self.wait.cancel)

                try:
                    tp, message = yield from self.wait
                    if tp == CLOSE:
                        session.closed()
                except tulip.CancelledError:
                    message = b'a[]'

                session.release()
                message = message + b'\n'

        headers = list(chain(
            (('Content-Type', 'application/javascript; charset=UTF-8'),
             ('Content-Length', str(len(message))),
             ('Cache-Control',
              'no-store, no-cache, must-revalidate, max-age=0')),
            session_cookie(request), cors_headers(environ)))

        start_response('200 Ok', headers)
        return (message,)
