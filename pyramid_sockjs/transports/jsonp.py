""" jsonp transport """
import uuid
from gevent.queue import Empty
from pyramid.compat import url_unquote
from pyramid.httpexceptions import HTTPBadRequest, HTTPServerError

from pyramid_sockjs import STATE_NEW
from pyramid_sockjs import STATE_OPEN
from pyramid_sockjs import STATE_CLOSING
from pyramid_sockjs import STATE_CLOSED
from pyramid_sockjs.protocol import OPEN, HEARTBEAT
from pyramid_sockjs.protocol import encode, decode, close_frame, message_frame

from .utils import session_cookie, cors_headers


timing = 5.0

def JSONPolling(session, request):
    meth = request.method
    response = request.response
    response.headers['Content-Type'] = 'application/javascript; charset=UTF-8'
    response.headerlist.append(
        ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0'))
    session_cookie(request)

    if session.state == STATE_NEW:
        callback = request.GET.get('c', None)
        if callback is None:
            return HTTPServerError('"callback" parameter required')

        response.text = '%s("o");\r\n' % callback
        session.open()
        session.release()

    elif meth == "GET":
        callback = request.GET.get('c', None)
        if callback is None:
            return HTTPServerError('"callback" parameter required')

        if session.state in (STATE_CLOSING, STATE_CLOSED):
            response.text = "%s(%s);\r\n"%(
                callback, encode(close_frame(3000, 'Go away!')))
            if session.state == STATE_CLOSING:
                session.closed()
        else:
            messages = []
            try:
                messages.append(session.get_transport_message(timeout=timing))
                while True:
                    try:
                        messages.append(
                            session.get_transport_message(block=False))
                    except Empty:
                        break

            except Empty:
                messages = HEARTBEAT
                session.heartbeat()
            else:
                messages = message_frame(messages)

            response.text = "%s(%s);\r\n"%(callback, encode(messages))

        session.release()

    elif meth == "POST":
        data = request.body_file.read()

        ctype = request.headers.get('Content-Type', '').lower()
        if ctype == 'application/x-www-form-urlencoded':
            if not data.startswith('d='):
                return HTTPServerError("Payload expected.")

            data = url_unquote(data[2:])

        if not data:
            return HTTPServerError("Payload expected.")

        try:
            messages = decode(data)
        except:
            return HTTPServerError("Broken JSON encoding.")

        for msg in messages:
            session.message(msg)

        response.status = 200
        response.headers['Content-Type'] = 'text/plain; charset=UTF-8'
        response.body = 'ok'
    else:
        raise Exception("No support for such method: %s"%meth)

    return response
