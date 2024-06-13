"""iframe-eventsource transport"""

from aiohttp import hdrs, web
from multidict import MultiDict

from .base import StreamingTransport
from .utils import CACHE_CONTROL, session_cookie


class EventsourceTransport(StreamingTransport):
    name = "eventsource"
    create_session = True

    async def _send(self, text: str):
        text = "".join(("data: ", text, "\r\n\r\n"))
        return await super()._send(text)

    async def process(self):
        headers = (
            (hdrs.CONTENT_TYPE, "text/event-stream"),
            (hdrs.CACHE_CONTROL, CACHE_CONTROL),
        )
        headers += session_cookie(self.request)

        # open sequence (sockjs protocol)
        resp = self.response = web.StreamResponse(headers=MultiDict(headers))
        await resp.prepare(self.request)
        # Opera needs one more new line at the start.
        await resp.write(b"\r\n")

        # handle session
        await self.handle_session()

        return resp
