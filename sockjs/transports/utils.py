import http.cookies
from aiohttp import hdrs
from datetime import datetime, timedelta


CACHE_CONTROL = 'no-store, no-cache, no-transform, must-revalidate, max-age=0'


def cors_headers(headers, nocreds=False):
    origin = headers.get(hdrs.ORIGIN, '*')
    cors = ((hdrs.ACCESS_CONTROL_ALLOW_ORIGIN, origin),)

    ac_headers = headers.get(hdrs.ACCESS_CONTROL_REQUEST_HEADERS)
    if ac_headers:
        cors += ((hdrs.ACCESS_CONTROL_ALLOW_HEADERS, ac_headers),)

    if origin != '*':
        return cors + ((hdrs.ACCESS_CONTROL_ALLOW_CREDENTIALS, 'true'),)
    else:
        return cors


def session_cookie(request):
    cookie = request.cookies.get('JSESSIONID', 'dummy')
    cookies = http.cookies.SimpleCookie()
    cookies['JSESSIONID'] = cookie
    cookies['JSESSIONID']['path'] = '/'
    return ((hdrs.SET_COOKIE, cookies['JSESSIONID'].output(header='')[1:]),)


td365 = timedelta(days=365)
td365seconds = str(
    int((td365.microseconds +
         (td365.seconds + td365.days*24*3600) * 10**6) / 10**6))


def cache_headers():
    d = datetime.now() + td365
    return (
        (hdrs.ACCESS_CONTROL_MAX_AGE, td365seconds),
        (hdrs.CACHE_CONTROL, 'max-age=%s, public' % td365seconds),
        (hdrs.EXPIRES, d.strftime('%a, %d %b %Y %H:%M:%S')),
    )
