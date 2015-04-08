""" iframe-eventsource transport """
import asyncio
from aiohttp import web, hdrs
from sockjs.protocol import ENCODING, STATE_CLOSING, close_frame
from sockjs.exceptions import SessionIsAcquired

from .base import StreamingTransport
from .utils import session_cookie


class EventsourceTransport(StreamingTransport):

    @asyncio.coroutine
    def send_text(self, text):
        blob = ''.join(('data: ', text, '\r\n\r\n')).encode(ENCODING)
        yield from self.response.write(blob)

        self.size += len(blob)
        if self.size > self.maxsize:
            yield from self.manager.release(self.session)
            self.waiter.set_result(True)

    def process(self):
        headers = list(
            ((hdrs.CONTENT_TYPE, 'text/event-stream; charset=UTF-8'),
             (hdrs.CACHE_CONTROL,
              'no-store, no-cache, must-revalidate, max-age=0')) +
            session_cookie(self.request))

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=headers)
        resp.start(self.request)
        resp.write(b'\r\n')

        # get session
        session = self.session

        # session was interrupted
        if session.interrupted:
            self.send_blob(close_frame(1002, b"Connection interrupted"))

        # session is closed
        elif session.state == STATE_CLOSING:
            yield from self.session._remote_closed()
            self.send_blob(close_frame(3000, b'Go away!'))

        else:
            # acquire session
            try:
                yield from self.manager.acquire(self.session, self)
            except SessionIsAcquired:
                yield from self.send_blob(
                    close_frame(2010, b"Another connection still open"))
            else:
                yield from self.waiter

        return resp
