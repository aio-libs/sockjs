""" iframe-eventsource transport """
import tulip
from itertools import chain
from pyramid.response import Response
from pyramid_sockjs.protocol import CLOSE, close_frame

from .base import Transport
from .utils import session_cookie


class EventsourceTransport(Transport):

    maxsize = 131072 # 128K bytes

    def __call__(self, environ, start_response):
        headers = list(
            chain(
                (('Content-Type','text/event-stream; charset=UTF-8'),
                 ('Cache-Control',
                  'no-store, no-cache, must-revalidate, max-age=0')),
                session_cookie(self.request)))

        write = start_response('200 Ok', headers)
        write(b'\r\n')

        # get session
        session = self.session
        try:
            session.acquire(self.request)
        except: # should use specific exception
            message = close_frame(2010, b"Another connection still open")
            write(b''.join((b'data: ', message, b'\r\n\r\n')))
            return b''

        try:
            size = 0

            while True:
                self.wait = tulip.Task(session.wait())
                try:
                    tp, message = yield from self.wait
                except tulip.CancelledError:
                    session.close()
                    session.closed()
                    break
                finally:
                    self.wait = None

                write(b''.join((b'data: ', message, b'\r\n\r\n')))

                if tp == CLOSE:
                    session.closed()
                    break

                size += len(message)
                if size >= self.maxsize:
                    break
        finally:
            session.release(self.interrupted)

        return b''
