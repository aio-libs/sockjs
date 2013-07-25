""" iframe-eventsource transport """
import tulip
from itertools import chain
from pyramid_sockjs import STATE_CLOSED
from pyramid_sockjs.protocol import CLOSE, close_frame
from pyramid_sockjs.exceptions import SessionIsAcquired

from .base import Transport
from .utils import session_cookie


class EventsourceTransport(Transport):

    maxsize = 131072  # 128K bytes

    def __call__(self, environ, start_response):
        headers = list(
            chain(
                (('Content-Type', 'text/event-stream; charset=UTF-8'),
                 ('Cache-Control',
                  'no-store, no-cache, must-revalidate, max-age=0')),
                session_cookie(self.request)))

        write = start_response('200 Ok', headers)
        write(b'\r\n')

        # get session
        session = self.session

        # session was interrupted
        if session.interrupted:
            write(close_frame(1002, b"Connection interrupted") + b'\n')

        # session is closed
        elif session.state == STATE_CLOSED:
            write(close_frame(3000, b'Go away!') + b'\n')

        else:
            try:
                session.acquire(self.request)
            except SessionIsAcquired:
                message = close_frame(2010, b"Another connection still open")
                write(b''.join((b'data: ', message, b'\r\n\r\n')))
                return (b'',)
            else:
                size = 0

                while size < self.maxsize:
                    try:
                        tp, message = yield from session.wait()
                    except tulip.CancelledError:
                        session.closed()
                        break
                    else:
                        write(b''.join((b'data: ', message, b'\r\n\r\n')))

                        if tp == CLOSE:
                            session.closed()
                            break

                        size += len(message)

                session.release()
        return ()
