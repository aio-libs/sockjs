import asyncio

from aiohttp import web
from multidict import CIMultiDict

from sockjs import protocol


def test_info(make_route, make_request):
    route = make_route()
    request = make_request('GET', '/sm/')

    response = route.info(request)
    info = protocol.loads(response.body.decode('utf-8'))

    assert info['websocket']
    assert info['cookie_needed']


def test_info_entropy(make_route, make_request):
    route = make_route()
    request = make_request('GET', '/sm/')

    response = route.info(request)
    entropy1 = protocol.loads(response.body.decode('utf-8'))['entropy']

    response = route.info(request)
    entropy2 = protocol.loads(response.body.decode('utf-8'))['entropy']

    assert entropy1 != entropy2


def test_info_options(make_route, make_request):
    route = make_route()
    request = make_request('OPTIONS', '/sm/')
    response = route.info_options(request)

    assert response.status == 204

    headers = response.headers
    assert 'Access-Control-Max-Age' in headers
    assert 'Cache-Control' in headers
    assert 'Expires' in headers
    assert 'Set-Cookie' in headers
    assert 'access-control-allow-credentials' in headers
    assert 'access-control-allow-origin' in headers


def test_greeting(make_route, make_request):
    route = make_route()
    request = make_request('GET', '/sm/')
    response = route.greeting(request)

    assert response.body == b'Welcome to SockJS!\n'


def test_iframe(make_route, make_request):
    route = make_route()
    request = make_request('GET', '/sm/')

    response = route.iframe(request)
    text = """<!DOCTYPE html>
<html>
<head>
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <script src="http:sockjs-cdn"></script>
  <script>
    document.domain = document.domain;
    SockJS.bootstrap_iframe();
  </script>
</head>
<body>
  <h2>Don't panic!</h2>
  <p>This is a SockJS hidden iframe. It's used for cross domain magic.</p>
</body>
</html>"""

    assert response.body.decode('utf-8') == text
    assert 'ETag' in response.headers


def test_iframe_cache(make_route, make_request):
    route = make_route()
    request = make_request(
        'GET', '/sm/',
        headers=CIMultiDict({'IF-NONE-MATCH': 'test'}))
    response = route.iframe(request)

    assert response.status == 304


async def test_handler_unknown_transport(make_route, make_request):
    route = make_route()
    request = make_request(
        'GET', '/sm/', match_info={'transport': 'unknown'})

    res = await route.handler(request)
    assert isinstance(res, web.HTTPNotFound)


async def test_handler_emptry_session(make_route, make_request):
    route = make_route()
    request = make_request(
        'GET', '/sm/',
        match_info={'transport': 'websocket', 'session': ''})
    res = await route.handler(request)
    assert isinstance(res, web.HTTPNotFound)


async def test_handler_bad_session_id(make_route, make_request):
    route = make_route()
    request = make_request(
        'GET', '/sm/',
        match_info={'transport': 'websocket',
                    'session': 'test.1', 'server': '000'})
    res = await route.handler(request)
    assert isinstance(res, web.HTTPNotFound)


async def test_handler_bad_server_id(make_route, make_request):
    route = make_route()
    request = make_request(
        'GET', '/sm/',
        match_info={'transport': 'websocket',
                    'session': 'test', 'server': 'test.1'})
    res = await route.handler(request)
    assert isinstance(res, web.HTTPNotFound)


async def test_new_session_before_read(make_route, make_request):
    route = make_route()
    request = make_request(
        'GET', '/sm/',
        match_info={
            'transport': 'xhr_send', 'session': 's1', 'server': '000'})
    res = await route.handler(request)
    assert isinstance(res, web.HTTPNotFound)


async def _test_transport(make_route, make_request):
    route = make_route()
    request = make_request(
        'GET', '/sm/',
        match_info={
            'transport': 'xhr', 'session': 's1', 'server': '000'})

    params = []

    class Transport:
        def __init__(self, manager, session, request):
            params.append((manager, session, request))

        def process(self):
            return web.HTTPOk()

    route = make_route(handlers={'test': (True, Transport)})
    res = await route.handler(request)
    assert isinstance(res, web.HTTPOk)
    assert params[0] == (route.manager, route.manager['s1'], request)


async def test_fail_transport(make_route, make_request):
    request = make_request(
        'GET', '/sm/',
        match_info={
            'transport': 'test', 'session': 'session', 'server': '000'})

    params = []

    class Transport:
        def __init__(self, manager, session, request):
            params.append((manager, session, request))

        def process(self):
            raise Exception('Error')

    route = make_route(handlers={'test': (True, Transport)})
    res = await route.handler(request)
    assert isinstance(res, web.HTTPInternalServerError)


async def test_release_session_for_failed_transport(make_route, make_request):
    request = make_request(
        'GET', '/sm/',
        match_info={
            'transport': 'test', 'session': 's1', 'server': '000'})

    class Transport:
        def __init__(self, manager, session, request):
            self.manager = manager
            self.session = session

        async def process(self):
            await self.manager.acquire(self.session)
            raise Exception('Error')

    route = make_route(handlers={'test': (True, Transport)})
    res = await route.handler(request)
    assert isinstance(res, web.HTTPInternalServerError)

    s1 = route.manager['s1']
    assert not route.manager.is_acquired(s1)


async def test_raw_websocket(loop, make_route, make_request, mocker):
    ws = mocker.patch('sockjs.route.RawWebSocketTransport')
    ws.return_value.process.return_value = asyncio.Future(loop=loop)
    ws.return_value.process.return_value.set_result(web.HTTPOk())

    route = make_route()
    request = make_request(
        'GET', '/sm/', headers=CIMultiDict({}))
    res = await route.websocket(request)

    assert isinstance(res, web.HTTPOk)
    assert ws.called
    assert ws.return_value.process.called


async def _test_raw_websocket_fail(make_route, make_request):
    route = make_route()
    request = make_request('GET', '/sm/')
    res = await route.websocket(request)
    assert not isinstance(res, web.HTTPNotFound)
