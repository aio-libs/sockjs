from gevent.queue import Empty
from datetime import datetime, timedelta

from pyramid_sockjs.protocol import HEARTBEAT, message_frame


def get_messages(session, timeout, heartbeat=True):
    messages = []
    try:
        messages.append(session.get_transport_message(timeout=timeout))
        while True:
            try:
                messages.append(session.get_transport_message(block=False))
            except Empty:
                break
    except Empty:
        if heartbeat:
            messages = HEARTBEAT
            session.heartbeat()
        else:
            messages = 'a[]'
    else:
        messages = message_frame(messages, '\n')

    return messages


def cors_headers(request):
    origin = request.environ.get("HTTP_ORIGIN", '*')
    return (('access-control-allow-origin', origin),
            ('access-control-allow-credentials', 'true'))


def session_cookie(request):
    cookie = request.cookies.get('JSESSIONID')

    if not cookie:
        cookie = 'dummy'

    request.response.set_cookie('JSESSIONID', cookie)
    return ('Set-Cookie', request.response.headers['Set-Cookie'])


td365 = timedelta(days=365)
td365seconds = int(td365.total_seconds())

def cache_headers(request):
    d = datetime.now() + td365

    return (
        ('Access-Control-Max-Age', td365seconds),
        ('Cache-Control', 'max-age=%d, public' % td365seconds),
        ('Expires', d.strftime('%a, %d %b %Y %H:%M:%S')),
        )
