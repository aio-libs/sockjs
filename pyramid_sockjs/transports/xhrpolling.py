import gevent
from gevent.queue import Empty
from pyramid.compat import url_unquote
from pyramid.response import Response
from pyramid.httpexceptions import HTTPBadRequest
from pyramid_sockjs.transports import StreamingStop
from pyramid_sockjs.protocol import OPEN, MESSAGE, HEARTBEAT
from pyramid_sockjs.protocol import decode, close_frame, message_frame


class PollingTransport(object):
    """ Long polling derivative transports, used for XHRPolling and JSONPolling.
    """

    TIMING = 5.0

    def __call__(self, session, request):
        meth = request.method

        if not session.connected and not session.expired:
            request.response.body = OPEN
            session.open()

        elif meth in ("GET", 'POST'):
            self.process(session, request)

        else:
            raise Exception("No support for such method: " + meth)

        session.manager.release(session)
        return request.response


class XHRPollingTransport(PollingTransport):

    def process(self, session, request):
        try:
            message = session.get_transport_message(timeout=self.TIMING)
        except Empty:
            message = '[]'

        request.response.body = message_frame(message)


class XHRSendPollingTransport(PollingTransport):

    def process(self, session, request):
        data = request.body_file.read()

        messages = decode(data)

        for msg in messages:
            session.message(msg)

        response = request.response
        response.headers = (("Content-Type", "text/html; charset=UTF-8"),)
        response.status = 204
