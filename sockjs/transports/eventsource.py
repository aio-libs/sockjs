""" iframe-eventsource transport """
import asyncio
from aiohttp import web, hdrs
from sockjs.protocol import ENCODING

from .base import StreamingTransport
from .utils import session_cookie


class EventsourceTransport(StreamingTransport):

    def send(self, text):
        blob = ''.join(('data: ', text, '\r\n\r\n')).encode(ENCODING)
        self.response.write(blob)

        self.size += len(blob)
        if self.size > self.maxsize:
            return True
        else:
            return False

    @asyncio.coroutine
    def process(self):
        headers = list(
            ((hdrs.CONTENT_TYPE, 'text/event-stream; charset=UTF-8'),
             (hdrs.CACHE_CONTROL,
              'no-store, no-cache, must-revalidate, max-age=0')) +
            session_cookie(self.request))

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=headers)
        yield from resp.prepare(self.request)
        resp.write(b'\r\n')

        # handle session
        yield from self.handle_session()

        return resp
