""" jsonp transport """
import tulip
from urllib.parse import unquote_plus
from pyramid.compat import url_unquote
from pyramid.response import Response
from pyramid.httpexceptions import HTTPBadRequest, HTTPServerError

from pyramid_sockjs import STATE_NEW
from pyramid_sockjs import STATE_OPEN
from pyramid_sockjs import STATE_CLOSING
from pyramid_sockjs import STATE_CLOSED
from pyramid_sockjs.protocol import OPEN, CLOSE
from pyramid_sockjs.protocol import encode, decode, close_frame, message_frame

from .utils import session_cookie, cors_headers


class JSONPolling(Response):

    timing = 5.0

    def __init__(self, session, request):
        self.__dict__.update(request.response.__dict__)
        self.session = session
        self.request = request

        self.headers['Content-Type'] = 'application/javascript; charset=UTF-8'
        self.headerlist.append(
            ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0'))
        self.headerlist.extend(session_cookie(request))

    def __call__(self, environ, start_response):
        session = self.session
        request = self.request

        meth = request.method
        response = request.response

        if meth == "GET":
            callback = request.GET.get('c', None)
            if callback is None:
                session.release()
                err = HTTPServerError('"callback" parameter required')
                return err(environ, start_response)

            if session.state == STATE_CLOSED:
                message = close_frame(3000, b'Go away!')
                body = b''.join((
                    callback.encode('utf-8'), b'(', encode(message), b');\r\n'))
                self.headers['Content-Length'] = str(len(body))

                write = start_response('200 Ok', self._abs_headerlist(environ))
                return (body,)

            # get session
            try:
                session.acquire(request, False)
            except: # should use specific exception
                #write(close_frame(2010, b"Another connection still open"))
                err = HTTPServerError(b"Another connection still open")
                return err(environ, start_response)

            self.wait = tulip.Task(tulip.wait((session.wait(),), self.timing))
            try:
                done, pending = yield from self.wait
                if done:
                    tp, message = done.pop().result()
                    if tp == CLOSE:
                        session.closed()
                else:
                    message = b'a[]'
            except tulip.CancelledError:
                session.close()
                session.closed()
                message = b''

            body = b''.join((
                callback.encode('utf-8'), b'(', encode(message), b');\r\n'))
            self.headers['Content-Length'] = str(len(body))

            write = start_response(self.status, self._abs_headerlist(environ))
            session.release()
            return (body,)

        elif meth == "POST":
            data = request.body_file.read()

            ctype = request.headers.get('Content-Type', '').lower()
            if ctype == 'application/x-www-form-urlencoded':
                if not data.startswith(b'd='):
                    err = HTTPServerError("Payload expected.")
                    return err(environ, start_response)

                data = unquote_plus(data[2:].decode('utf-8'))

            if not data:
                err = HTTPServerError("Payload expected.")
                return err(environ, start_response)

            try:
                messages = decode(data)
            except:
                err = HTTPServerError("Broken JSON encoding.")
                return err(environ, start_response)

            for msg in messages:
                session.message(msg)

            body = b'ok'
            self.status = 200
            self.headers['Content-Type'] = 'text/plain; charset=UTF-8'
            self.headers['Content-Length'] = str(len(body))
            write = start_response(self.status, self._abs_headerlist(environ))
            write(body)

        else:
            raise Exception("No support for such method: %s"%meth)

        return (b'',)
