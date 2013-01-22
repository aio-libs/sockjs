import tulip
from webob.cookies import Morsel
from pyramid_sockjs import STATE_CLOSED
from pyramid_sockjs.protocol import CLOSE, close_frame
from pyramid_sockjs.exceptions import SessionIsAcquired

from .base import Transport
from .utils import session_cookie, cors_headers, cache_headers

from pprint import pprint


class XHRStreamingTransport(Transport):

    maxsize = 131072 # 128K bytes
    open_seq = b'h' *  2048 + b'\n'

    def __init__(self, session, request):
        super(XHRStreamingTransport, self).__init__(session, request)

        if request.method not in ('GET', 'POST', 'OPTIONS'):
            raise Exception("No support for such method: %s"%meth)

    def __call__(self, environ, start_response):
        request = self.request
        headers = list(
            (('Connection', 'close'),
             ('Content-Type', 'application/javascript; charset=UTF-8'),
             ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
         ) + session_cookie(request) + cors_headers(environ))

        if request.method == 'OPTIONS':
            headers.append(
                ("Access-Control-Allow-Methods", "OPTIONS, POST"))
            headers.extend(cache_headers())
            start_response('204 No Content', headers)
            return b''

        # open sequence (sockjs protocol)
        write = start_response('200 Ok', headers)
        write(self.open_seq)

        session = self.session

        # session was interrupted
        if session.interrupted:
            write(close_frame(1002, b"Connection interrupted")+b'\n')

        # session is closed
        elif session.state == STATE_CLOSED:
            write(close_frame(3000, b'Go away!')+b'\n')

        else:
            # acquire session
            try:
                session.acquire(self.request)
            except SessionIsAcquired:
                write(close_frame(2010, b"Another connection still open")+b'\n')
            else:
                # message loop
                try:
                    size = 0

                    while size < self.maxsize:
                        self.wait = tulip.Task(session.wait())
                        try:
                            tp, message = yield from self.wait
                        except tulip.CancelledError:
                            break
                        finally:
                            self.wait = None

                        write(message+b'\n')

                        if tp == CLOSE:
                            session.closed()
                            break

                        # sockjs api (limit for one streaming connection)
                        size += len(message)

                finally:
                    session.release()

        return b''
