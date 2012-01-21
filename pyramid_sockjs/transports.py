import gevent
from gevent.queue import Empty
from pyramid.response import Response
from pyramid_sockjs.protocol import OPEN
from pyramid_sockjs.protocol import encode, decode, close_frame, message_frame

def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type('Enum', (), enums)


class PollingTransport(object):
    """
    Long polling derivative transports, used for XHRPolling and
    JSONPolling.

    Subclasses overload the write_frame method for their
    respective serialization methods.
    """

    TIMING = 5.0

    def options(self, request):
        request.response.headers = (
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Credentials", "true"),
            ("Access-Control-Allow-Methods", "POST, GET, OPTIONS"),
            ("Access-Control-Max-Age", 3600),
            ("Connection", "close"),
            ("Content-Length", 0)
            )

    def get(self, session, request):
        """
        Spin lock the thread until we have a message on the
        gevent queue.
        """
        try:
            messages = session.get_messages(timeout=self.TIMING)
        except Empty:
            messages = '[]'

        request.response.headers = {
            "Access-Control-Allow-Origin": "*",
            "Connection": "close"}

        request.response.body = message_frame(messages)

    def post(self, session, request):
        raise NotImplemented

    def __call__(self, session, request):
        """
        Initial starting point for this handler's thread,
        delegates to another method depending on the session,
        request method, and action.
        """
        meth = request.method
        
        if session.is_new():
            request.response.body = OPEN

        elif meth == "GET":
            session.clear_disconnect_timeout();
            self.get(session, request)

        elif meth == "POST":
            self.post(session, request)

        elif meth == "OPTIONS":
            self.options(request)

        else:
            raise Exception("No support for such method: " + request_method)

        return request.response


class XHRPollingTransport(PollingTransport):

    post = PollingTransport.get


class XHRSendPollingTransport(PollingTransport):

    def post(self, session, request):
        data = self.handler.wsgi_input.readline()#.replace("data=", "")

        messages = decode(data)

        for msg in messages:
            session.add_message(messages)

        self.content_type = ("Content-Type", "text/html; charset=UTF-8")
        self.start_response("204 NO CONTENT", [])
        self.write(None)


def XHRStreamingTransport(session, request,
                          INIT_STREAM = 'h' *  2048 + '\n' + OPEN):
    meth = request.environ['REQUEST_METHOD']

    if session.is_new():
        request.response.app_iter = XHRStreamingIterator(session, INIT_STREAM)

    elif meth == "GET":
        request.response.app_iter = XHRStreamingIterator(session)

    elif meth == "POST":
        request.response.app_iter = XHRStreamingIterator(session)

    elif meth == "OPTIONS":
        self.options(request)

    else:
        raise Exception("No support for such method: " + request_method)

    return request.response


class XHRStreamingIterator(object):

    def __init__(self, session, init=None):
        self.session = session
        self.init = init
        self.init_sent = False

    def __iter__(self):
        return self

    def next(self):
        if self.init and not self.init_sent:
            self.init_sent = True
            return self.init

        while True:
            try:
                message = self.session.get_messages(timeout=5.0)
            except Empty:
                message = '["test"]'
                #continue

            if message is None:
                session.kill()
                raise StopIteration()

            return message_frame(message)

    __next__ = next


class JSONPolling(PollingTransport):
    pass


class HTMLFileTransport(object):
    pass


class IFrameTransport(object):
    pass


def WebSocketTransport(session, request):

    def send():
        session.incr_hits()
        websocket = request.environ['wsgi.websocket']
        websocket.send(OPEN)

        while True:
                try:
                    message = session.get_messages(timeout=5.0)
                except Empty:
                    message = '["TEST"]'

                if message is None:
                    session.kill()
                    break

                websocket.send(message_frame(message))

    jobs = [gevent.spawn(send)]

    response = request.response
    response.app_iter = WebSocketIterator(response.app_iter, jobs)
    return response


class WebSocketIterator(list):

    def __init__(self, app_iter, jobs):
        self.extend(app_iter)
        self.jobs = jobs

    def close(self):
        gevent.joinall(self.jobs)
