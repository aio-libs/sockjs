""" iframe-htmlfile transport """
import tulip
from itertools import chain
from pyramid_sockjs.protocol import CLOSE, close_frame, encode
from pyramid_sockjs.exceptions import SessionIsAcquired

from .base import Transport
from .utils import session_cookie, cors_headers


PRELUDE1 = b"""
<!doctype html>
<html><head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head><body><h2>Don't panic!</h2>
  <script>
    document.domain = document.domain;
    var c = parent."""

PRELUDE2 = b""";
    c.start();
    function p(d) {c.message(d);};
    window.onload = function() {c.stop();};
  </script>"""


class HTMLFileTransport(Transport):

    maxsize = 131072 # 128K bytes

    def __call__(self, environ, start_response):
        session = self.session
        request = self.request

        headers = list(chain(
            (('Content-Type', 'text/html; charset=UTF-8'),
             ('Cache-Control','no-store, no-cache, must-revalidate, max-age=0'),
             ("Connection", "close")),
            session_cookie(request), cors_headers(environ)))

        callback = request.GET.get('c', None)
        if callback is None:
            start_response('500 Internal Server Error', headers)
            return (b'"callback" parameter required',)

        write = start_response('200 Ok', headers)
        write(b''.join((PRELUDE1,callback.encode('utf-8'),PRELUDE2,b' '*1024)))

        # get session
        session = self.session
        try:
            session.acquire(self.request)
        except SessionIsAcquired:
            write(close_frame(2010, b"Another connection still open"))
        else:
            size = 0
            while size < self.maxsize:
                self.wait = tulip.Task(tulip.wait((session.wait(),)))
                try:
                    tp, msg = (yield from self.wait)[0].pop().result()
                except tulip.CancelledError:
                    session.close()
                    session.closed()
                else:
                    write(b''.join(
                        (b'<script>\np(', encode(msg), b');\n</script>\r\n')))

                    if tp == CLOSE:
                        session.closed()
                        break

                    size += len(msg)

            session.release()

        return ()
