""" iframe-htmlfile transport """
import gevent
from gevent.queue import Empty
from pyramid.compat import url_unquote
from pyramid.response import Response
from pyramid_sockjs.transports import StreamingStop
from pyramid_sockjs.protocol import HEARTBEAT
from pyramid_sockjs.protocol import encode, decode, close_frame, message_frame


PRELUDE = r'''
<!doctype html>
<html><head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head><body><h2>Don't panic!</h2>
  <script>
    document.domain = document.domain;
    var c = parent.%s;
    c.start();
    function p(d) {c.message(d);};
    window.onload = function() {c.stop();};
  </script>
'''.strip()


def HTMLFileTransport(session, request):
    response = request.response

    callback = request.GET.get('c', None)
    if callback is None:
        raise Exception('"callback" parameter is required')

    prelude = PRELUDE % callback
    prelude += ' ' * (1024 - len(prelude))

    session.open()

    return HTMLFileResponse(request.response, session, prelude)


class HTMLFileResponse(Response):

    TIMING = 5.0

    def __init__(self, response, session, prelude=''):
        self.__dict__.update(response.__dict__)
        self.session = session
        self.prelude = prelude

    def __call__(self, environ, start_response):
        write = start_response(
            self.status, (('Content-Type', 'text/html; charset=UTF-8'),))
        write(self.prelude)
        write("<script>\np('o');\n</script>\r\n")

        timing = self.TIMING
        session = self.session

        try:
            while True:
                try:
                    message = session.get_transport_message(timeout=timing)
                    if message is None:
                        session.close()
                        write("<script>\np(%s);\n</script>\r\n" %
                              encode(close_frame('Go away!')))
                        raise StopIteration()
                except Empty:
                    message = HEARTBEAT
                    session.heartbeat()
                else:
                    message = message_frame(message)

                if not session.connected:
                    write("<script>\np(%s);\n</script>\r\n" %
                          encode(close_frame('Go away!')))
                    break

                try:
                    write("<script>\np(%s);\n</script>\r\n" % encode(message))
                except:
                    session.close()
                    raise StreamingStop()
        finally:
            session.manager.release(session)

        return []
