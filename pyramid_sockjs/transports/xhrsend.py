from zope.interface import implementer
from pyramid.interfaces import IResponse
from pyramid.httpexceptions import HTTPForbidden, HTTPServerError
from pyramid_sockjs.protocol import decode

from .utils import session_cookie, cors_headers, cache_headers


@implementer(IResponse)

class XHRSendTransport:

    def __init__(self, session, request):
        self.session = session
        self.request = request

    def __call__(self, environ, start_response):
        request = self.request

        if request.method not in ('GET', 'POST', 'OPTIONS'):
            err = HTTPForbidden("Method is not allowed")
            return err(environ, start_response)

        if self.request.method == 'OPTIONS':
            headers = list(
                (("Access-Control-Allow-Methods", "OPTIONS, POST"),
                 ('Content-Type', 'application/javascript; charset=UTF-8')) +
                session_cookie(request) + 
                cors_headers(environ) + 
                cache_headers())
            start_response('204 No Content', headers)
            return (b'',)

        data = request.body_file.read()
        if not data:
            err = HTTPServerError("Payload expected.")
            return err(environ, start_response)

        try:
            messages = decode(data)
        except:
            err = HTTPServerError("Broken JSON encoding.")
            return err(environ, start_response)

        for msg in messages:
            self.session.message(msg)

        headers = list(
            (('Content-Type', 'text/plain; charset=UTF-8'),
             ('Cache-Control',
              'no-store, no-cache, must-revalidate, max-age=0')) +
            session_cookie(request) + cors_headers(environ))

        start_response('204 No Content', headers)
        return (b'',)
