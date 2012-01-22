import gevent
from gevent.queue import Empty
from pyramid.compat import url_unquote
from pyramid.httpexceptions import HTTPBadRequest
from pyramid_sockjs.protocol import OPEN, MESSAGE
from pyramid_sockjs.protocol import encode, decode, close_frame, message_frame

def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type('Enum', (), enums)


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
            messages = session._messages(timeout=self.TIMING)
        except Empty:
            messages = '[]'

        request.response.body = message_frame(messages)


class XHRSendPollingTransport(PollingTransport):

    def process(self, session, request):
        data = request.body_file.read()

        messages = decode(data)

        for msg in messages:
            session.message(msg)

        response = request.response
        response.headers = (("Content-Type", "text/html; charset=UTF-8"),)
        response.status = 204


def XHRStreamingTransport(session, request,
                          INIT_STREAM = 'h' *  2048 + '\n' + OPEN):
    meth = request.environ['REQUEST_METHOD']
    input = request.environ['wsgi.input']

    if not session.connected and not session.expired:
        request.response.app_iter = XHRStreamingIterator(
            session, INIT_STREAM, input=input)
        session.open()

    elif meth in ('GET', 'POST'):
        request.response.app_iter = XHRStreamingIterator(session, input=input)

    else:
        raise Exception("No support for such method: " + request_method)

    return request.response


from geventwebsocket.websocket import _get_write

class XHRStreamingIterator(object):

    def __init__(self, session, init=None, input=None):
        self.session = session
        self.init = init
        self.init_sent = False
        self.write = _get_write(input.rfile)
        self.rfile = input.rfile

    def __iter__(self):
        return self

    def next(self):
        if self.init and not self.init_sent:
            self.init_sent = True
            return self.init

        while True:
            try:
                message = self.session._messages(timeout=5.0)
            except Empty:
                continue

            if message is None:
                session.close()
                raise StopIteration()

            if not self.session.connected:
                break

            print (self.rfile.closed,)
            try:
                self.write(message_frame(message))
            except:
                import traceback
                traceback.print_exc()
                self.session.close()
                break

    __next__ = next


def JSONPolling(session, request):
    meth = request.method
    response = request.response
    response.headers['Content-Type'] = 'application/javascript; charset=UTF-8'

    if not session.connected and not session.expired:
        callback = request.GET.get('c', None)
        if callback is None:
            raise Exception('"callback" parameter is required')

        response.text = '%s("o");\r\n' % callback
        session.open()

    elif meth == "GET":
        callback = request.GET.get('c', None)
        if callback is None:
            raise Exception('"callback" parameter is required')

        try:
            messages = session._messages(timeout=self.TIMING)
        except Empty:
            messages = '[]'
        response.text = "%s('%s%s');\r\n"%(callback, MESSAGE, encode(messages))

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


class HTMLFileTransport(object):
    pass


class IFrameTransport(object):
    pass


def WebSocketTransport(session, request):
    websocket = request.environ['wsgi.websocket']

    def send():
        websocket.send(OPEN)
        session.open()

        while True:
            try:
                message = session._messages(2.0)
            except Empty:
                continue

            if message is None:
                websocket.send(close_frame('Go away'))
                websocket.close()
                session.close()
                break

            if not session.connected:
                break

            try:
                websocket.send(message_frame(message))
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
