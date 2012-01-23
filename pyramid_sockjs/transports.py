import gevent
from gevent.queue import Empty
from pyramid.compat import url_unquote
from pyramid.httpexceptions import HTTPBadRequest
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


from gevent.pywsgi import WSGIHandler

class XHRStreamingStop(Exception):
    """ """

orig_handle_error = WSGIHandler.handle_error

def handle_error(self, type, value, tb):
    if issubclass(type, XHRStreamingStop):
        del tb
        return

    return orig_handle_error(self, type, value, tb)

WSGIHandler.handle_error = handle_error


def XHRStreamingTransport(session, request,
                          INIT_STREAM = 'h' *  2048 + '\n' + OPEN):
    meth = request.method
    input = request.environ['wsgi.input']
    request.response.headers = (
        ('Content-Type', 'text/html; charset=UTF-8'),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Credentials", "true"),
        ("Access-Control-Allow-Methods", "POST, GET, OPTIONS"),
        ("Access-Control-Max-Age", 3600),
        ("Connection", "close"))

    if not session.connected and not session.expired:
        request.response.app_iter = XHRStreamingIterator(
            session, INIT_STREAM, input)
        session.open()

    elif meth in ('GET', 'POST'):
        request.response.app_iter = XHRStreamingIterator(session, input=input)

    else:
        raise Exception("No support for such method: %s"%meth)

    return request.response


from geventwebsocket.websocket import _get_write

class XHRStreamingIterator(object):

    TIMING = 5.0

    def __init__(self, session, init_stream=None, input=None):
        self.session = session
        self.init_stream = init_stream
        self.write = _get_write(input.rfile)

    def __iter__(self):
        return self

    def next(self):
        if self.init_stream:
            self.write(self.init_stream)

        timing = self.TIMING
        session = self.session

        while True:
            try:
                message = session.get_transport_message(timeout=timing)
                if message is None:
                    session.close()
                    raise StopIteration()
            except Empty:
                message = HEARTBEAT
                session.heartbeat()
            else:
                message = message_frame(message)

            if not session.connected:
                raise StopIteration()

            try:
                self.write(message)
            except:
                session.close()
                raise XHRStreamingStop()

    __next__ = next


def JSONPolling(session, request):
    meth = request.method
    response = request.response
    response.headers['Content-Type'] = 'application/javascript; charset=UTF-8'

    if not session.connected and not session.expired:
        callback = request.GET.get('c', None)
        if callback is None:
            raise Exception('"callback" parameter is required')

        response.text = '%s("o");' % callback
        session.open()

    elif meth == "GET":
        callback = request.GET.get('c', None)
        if callback is None:
            raise Exception('"callback" parameter is required')

        try:
            message = session.get_transport_message(timeout=5.0)
        except Empty:
            message = '[]'
        response.text = "%s('%s%s');\r\n"%(callback, MESSAGE, message)

    elif meth == "POST":
        data = request.body_file.read()

        ctype = request.headers.get('Content-Type', '').lower()
        if ctype == 'application/x-www-form-urlencoded':
            if not data.startswith('d='):
                raise Exception("Payload expected.")

        data = url_unquote(data[2:])

        messages = decode(data)
        for msg in messages:
            session.message(msg)

        response.status = 204
    else:
        raise Exception("No support for such method: %s"%meth)

    session.manager.release(session)
    return request.response


def WebSocketTransport(session, request):
    websocket = request.environ['wsgi.websocket']

    def send():
        websocket.send(OPEN)
        session.open()

        while True:
            try:
                message = session.get_transport_message(5.0)
            except Empty:
                message = HEARTBEAT
                session.heartbeat()
            else:
                message = message_frame(message)

            if message is None:
                websocket.send(close_frame('Go away'))
                websocket.close()
                session.close()
                break

            if not session.connected:
                break

            try:
                websocket.send(message)
            except:
                session.close()
                break

    def receive():
        while True:
            message = websocket.receive()

            if not message:
                session.close()
                break
            else:
                decoded_message = decode(message)
                if decoded_message is not None:
                    session.message(decoded_message)

    jobs = [gevent.spawn(send), gevent.spawn(receive)]

    response = request.response
    response.app_iter = WebSocketIterator(response.app_iter, jobs)
    return response


class WebSocketIterator(list):

    def __init__(self, app_iter, jobs):
        self.extend(app_iter)
        self.jobs = jobs

    def close(self):
        gevent.joinall(self.jobs)
