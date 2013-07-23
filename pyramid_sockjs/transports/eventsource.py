""" iframe-eventsource transport """
import tulip
from itertools import chain
from pyramid_sockjs.protocol import CLOSE, close_frame

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
        try:
            session.acquire(self.request)
        except:  # should use specific exception
            message = close_frame(2010, b"Another connection still open")
            write(b''.join((b'data: ', message, b'\r\n\r\n')))
            return (b'',)

        size = 0

        while size < self.maxsize:
            self.wait = tulip.Task(tulip.wait((session.wait(),)))
            try:
                tp, message = (yield from self.wait)[0].pop().result()
            except tulip.CancelledError:
                session.close()
                session.closed()
            else:
                write(b''.join((b'data: ', message, b'\r\n\r\n')))

                if tp == CLOSE:
                    session.closed()
                    break

                size += len(message)

        session.release()
        return ()
