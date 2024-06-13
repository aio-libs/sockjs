"""jsonp transport"""

import re
from urllib.parse import unquote_plus

from aiohttp import hdrs, web
from multidict import MultiDict

from .base import StreamingTransport
from .utils import CACHE_CONTROL, session_cookie
from ..protocol import ENCODING, dumps, loads


class JSONPolling(StreamingTransport):
    name = "jsonp-polling"
    create_session = True
    maxsize = 0
    check_callback = re.compile(r"^[a-zA-Z0-9_\.]+$")
    callback = ""

    async def _send(self, text: str):
        text = "/**/%s(%s);\r\n" % (self.callback, dumps(text))
        return await super()._send(text)

    async def process(self):
        manager = self.manager
        session = self.session
        request = self.request
        meth = request.method

        if request.method == hdrs.METH_GET:
            callback = self.callback = request.query.get("c")
            if not callback:
                await self.manager.remote_closed(self.session)
                raise web.HTTPInternalServerError(text='"callback" parameter required')

            elif not self.check_callback.match(callback):
                await self.manager.remote_closed(self.session)
                raise web.HTTPInternalServerError(text='invalid "callback" parameter')

            headers = (
                (hdrs.CONTENT_TYPE, "application/javascript; charset=UTF-8"),
                (hdrs.CACHE_CONTROL, CACHE_CONTROL),
            )
            headers += session_cookie(request)

            resp = self.response = web.StreamResponse(headers=MultiDict(headers))
            await resp.prepare(request)

            await self.handle_session()
            return resp

        elif request.method == hdrs.METH_POST:
            data = await request.read()

            ctype = request.content_type.lower()
            if ctype == "application/x-www-form-urlencoded":
                if not data.startswith(b"d="):
                    raise web.HTTPInternalServerError(text="Payload expected.")

                data = unquote_plus(data[2:].decode(ENCODING))
            else:
                data = data.decode(ENCODING)

            if not data:
                raise web.HTTPInternalServerError(text="Payload expected.")

            try:
                messages = loads(data)
            except Exception:
                raise web.HTTPInternalServerError(text="Broken JSON encoding.")

            await manager.remote_messages(session, messages)

            headers = (
                (hdrs.CONTENT_TYPE, "text/plain;charset=UTF-8"),
                (hdrs.CACHE_CONTROL, CACHE_CONTROL),
            )
            headers += session_cookie(request)
            return web.Response(body=b"ok", headers=MultiDict(headers))

        else:
            raise web.HTTPBadRequest(text="No support for such method: %s" % meth)


class JSONPollingSend(JSONPolling):
    name = "jsonp-polling"
    create_session = False
