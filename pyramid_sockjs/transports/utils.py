

def session_cookie(request):
    cookie = request.cookies.get('JSESSIONID')

    if not cookie:
        cookie = 'dummy'

    request.response.set_cookie('JSESSIONID', cookie)
    return ('Set-Cookie', request.response.headers['Set-Cookie'])
