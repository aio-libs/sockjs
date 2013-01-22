from webob.cookies import Morsel
from datetime import datetime, timedelta


def cors_headers(environ):
    origin = environ.get("HTTP_ORIGIN", '*')
    if origin == 'null':
        origin = '*'
    ac_headers = environ.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS')
    if ac_headers is not None:
        return (('access-control-allow-origin', origin),
                ('access-control-allow-credentials', 'true'),
                ('access-control-allow-headers', ac_headers))
    else:
        return (('access-control-allow-origin', origin),
                ('access-control-allow-credentials', 'true'))


def session_cookie(request):
    cookie = request.cookies.get('JSESSIONID', b'dummy')
    if isinstance(cookie, str):
        cookie = cookie.encode('utf-8')

    m = Morsel(b'JSESSIONID', cookie)
    m.path = b'/'

    return (('Set-Cookie', m.serialize()),)


td365 = timedelta(days=365)
td365seconds = int((td365.microseconds +
                    (td365.seconds + td365.days*24*3600) * 10**6) / 10**6)

def cache_headers():
    d = datetime.now() + td365
    return (
        ('Access-Control-Max-Age', td365seconds),
        ('Cache-Control', 'max-age=%d, public' % td365seconds),
        ('Expires', d.strftime('%a, %d %b %Y %H:%M:%S')),
        )
