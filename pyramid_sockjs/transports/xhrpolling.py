import gevent
from gevent.queue import Empty
from pyramid.compat import url_unquote
from pyramid.response import Response
from pyramid.httpexceptions import HTTPBadRequest, HTTPServerError

from pyramid_sockjs import STATE_NEW
from pyramid_sockjs import STATE_OPEN
from pyramid_sockjs import STATE_CLOSING
from pyramid_sockjs import STATE_CLOSED

from pyramid_sockjs.protocol import OPEN, MESSAGE, HEARTBEAT
from pyramid_sockjs.protocol import decode, close_frame, message_frame

from .utils import get_messages, session_cookie, cors_headers, cache_headers


class PollingTransport(object):
    """ Long polling derivative transports, used for XHRPolling and JSONPolling.
    """
    timing = 5.0
    heartbeat = False

    def __call__(self, session, request):
        meth = request.method
        session_cookie(request)
        response = request.response

        if meth in ('GET', 'POST'):
            result = self.process(session, request)
            if result is not None:
                return result
        elif meth == 'OPTIONS':
            response.status = 204
            response.content_type = 'application/javascript; charset=UTF-8'
            response.headerlist.append(
                ("Access-Control-Allow-Methods", "OPTIONS, POST"))
            response.headerlist.extend(cors_headers(request))
            response.headerlist.extend(cache_headers(request))
        else:
            raise Exception("No support for such method: " + meth)

        return response


class XHRPollingTransport(PollingTransport):

    method = 'GET'

    def process(self, session, request):
        response = request.response
        response.content_type = 'application/javascript; charset=UTF-8'
        response.headerlist.extend(cors_headers(request))

        def finish(request):
            session.release()

        request.add_finished_callback(finish)

        try:
            session.acquire(request)
        except: # should use specific exception
            response.body = close_frame(
                2010, "Another connection still open", '\n')
            return

        if session.state == STATE_NEW:
            response.body = OPEN
            session.open()
            return

        if session.state in (STATE_CLOSING, STATE_CLOSED):
            response.body = close_frame(3000, 'Go away!', '\n')
            if session.state == STATE_CLOSING:
                session.closed()
            return

        response.body = get_messages(session, self.timing, self.heartbeat)


class XHRSendPollingTransport(PollingTransport):

    method = 'POST'

    def process(self, session, request):
        response = request.response
        response.content_type = 'text/plain; charset=UTF-8'
        response.headerlist.extend(cors_headers(request))

        data = request.body_file.read()
        if not data:
            return HTTPServerError("Payload expected.")

        try:
            messages = decode(data)
        except:
            return HTTPServerError("Broken JSON encoding.")

        for msg in messages:
            session.message(msg)

        response.status = 204
