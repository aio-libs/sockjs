"""jsonp transport"""
import re
from urllib.parse import unquote_plus

from aiohttp import web, hdrs

from .base import StreamingTransport
from .utils import session_cookie, cors_headers
from ..protocol import dumps, loads, ENCODING


class JSONPolling(StreamingTransport):

    timeout = 5.0
    check_callback = re.compile('^[a-zA-Z0-9_\.]+$')
    callback = ''

    def send(self, text):
        blob = ('%s(%s);\r\n' % (self.callback, dumps(text))).encode(ENCODING)
        self.response.write(blob)
        return True

    def process(self):
        session = self.session
        request = self.request
        meth = request.method

        if request.method == hdrs.METH_GET:

            callback = self.callback = request.GET.get('c')
            if not callback:
                yield from self.session._remote_closed()
                return web.HTTPBadRequest(
                    body=b'"callback" parameter required')

            elif not self.check_callback.match(callback):
                yield from self.session._remote_closed()
                return web.HTTPBadRequest(
                    body=b'invalid "callback" parameter')

            headers = list(
                ((hdrs.CONTENT_TYPE,
                  'application/javascript; charset=UTF-8'),
                 (hdrs.CACHE_CONTROL,
                  'no-store, no-cache, must-revalidate, max-age=0')) +
                session_cookie(request) +
                cors_headers(request.headers))

            resp = self.response = web.StreamResponse(headers=headers)
            resp.start(request)

            yield from self.handle_session()
            return resp

        elif request.method == hdrs.METH_POST:
            data = yield from request.read()

            ctype = request.content_type.lower()
            if ctype == 'application/x-www-form-urlencoded':
                if not data.startswith(b'd='):
                    return web.HTTPBadRequest(body=b'Payload expected.')

                data = unquote_plus(data[2:].decode(ENCODING))
            else:
                data = data.decode(ENCODING)

            if not data:
                return web.HTTPBadRequest(body=b'Payload expected.')

            try:
                messages = loads(data)
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
            return web.HTTPBadRequest(
                text="No support for such method: %s" % meth)
