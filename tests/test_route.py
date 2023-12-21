import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from cykooz.testing import D
from multidict import CIMultiDict

from sockjs import protocol
from sockjs.route import ALL_METH_WO_OPTIONS
from sockjs.transports import transport_handlers
from sockjs.transports.base import Transport


async def test_info(make_route, make_request):
    route = make_route()
    request = make_request("GET", "/sm/")

    response = await route.info(request)
    info = protocol.loads(response.body.decode("utf-8"))

    assert info["websocket"]
    assert info["cookie_needed"]
    assert info["transports"] == [
        "eventsource",
        "htmlfile",
        "jsonp-polling",
        "websocket",
        "websocket-raw",
        "xhr-polling",
        "xhr-streaming",
    ]


async def test_info_entropy(make_route, make_request):
    route = make_route()
    request = make_request("GET", "/sm/")

    response = await route.info(request)
    entropy1 = protocol.loads(response.body.decode("utf-8"))["entropy"]

    response = await route.info(request)
    entropy2 = protocol.loads(response.body.decode("utf-8"))["entropy"]

    assert entropy1 != entropy2


async def test_greeting(make_route, make_request):
    route = make_route()
    request = make_request("GET", "/sm/")
    response = await route.greeting(request)

    assert response.body == b"Welcome to SockJS!\n"


async def test_iframe(make_route, make_request):
    route = make_route()
    request = make_request("GET", "/sm/")

    response = await route.iframe(request)
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

    assert response.body.decode("utf-8") == text
    assert "ETag" in response.headers


async def test_iframe_cache(make_route, make_request):
    route = make_route()
    request = make_request(
        "GET", "/sm/", headers=CIMultiDict({"IF-NONE-MATCH": "test"})
    )
    response = await route.iframe(request)

    assert response.status == 304


async def test_handler_unknown_transport(make_route, make_request):
    route = make_route()
    request = make_request("GET", "/sm/", match_info={"transport": "unknown"})

    with pytest.raises(web.HTTPNotFound):
        await route.handler(request)


async def test_handler_emptry_session(make_route, make_request):
    route = make_route()
    request = make_request(
        "GET", "/sm/", match_info={"transport": "websocket", "session": ""}
    )
    with pytest.raises(web.HTTPNotFound):
        await route.handler(request)


async def test_handler_bad_session_id(make_route, make_request):
    route = make_route()
    request = make_request(
        "GET",
        "/sm/",
        match_info={"transport": "websocket", "session": "test.1", "server": "000"},
    )
    with pytest.raises(web.HTTPNotFound):
        await route.handler(request)


async def test_handler_bad_server_id(make_route, make_request):
    route = make_route()
    request = make_request(
        "GET",
        "/sm/",
        match_info={"transport": "websocket", "session": "test", "server": "test.1"},
    )
    with pytest.raises(web.HTTPNotFound):
        await route.handler(request)


async def test_new_session_before_read(make_route, make_request):
    route = make_route()
    request = make_request(
        "GET",
        "/sm/",
        match_info={"transport": "xhr_send", "session": "s1", "server": "000"},
    )
    with pytest.raises(web.HTTPNotFound):
        await route.handler(request)


async def _test_transport(make_route, make_request):
    route = make_route()
    request = make_request(
        "GET", "/sm/", match_info={"transport": "xhr", "session": "s1", "server": "000"}
    )

    params = []

    class FakeTransport(Transport):
        def __init__(self, manager, session, request):
            super().__init__(manager, session, request)
            params.append((manager, session, request))

        def process(self):
            return web.HTTPOk()

    route = make_route(handlers={"test": FakeTransport})
    res = await route.handler(request)
    assert isinstance(res, web.HTTPOk)
    assert params[0] == (route.manager, route.manager["s1"], request)


async def test_fail_transport(make_route, make_request):
    request = make_request(
        "GET",
        "/sm/",
        match_info={"transport": "test", "session": "session", "server": "000"},
    )

    params = []

    class FakeTransport(Transport):
        name = "test"

        def __init__(self, manager, session, request):
            super().__init__(manager, session, request)
            params.append((manager, session, request))

        def process(self):
            raise Exception("Error")

    route = make_route(handlers={"test": FakeTransport})
    with pytest.raises(web.HTTPInternalServerError):
        await route.handler(request)


async def test_release_session_for_failed_transport(make_route, make_request):
    request = make_request(
        "GET",
        "/sm/",
        match_info={"transport": "test", "session": "s1", "server": "000"},
    )

    class FakeTransport(Transport):
        name = "test"
        create_session = True

        async def process(self):
            await self.manager.acquire(self.session, self.request)
            raise Exception("Error")

    route = make_route(handlers={"test": FakeTransport})
    with pytest.raises(web.HTTPInternalServerError):
        await route.handler(request)

    s1 = route.manager.sessions["s1"]
    assert not route.manager.is_acquired(s1)


async def test_raw_websocket(make_route, make_request, mocker):
    ws = mocker.patch("sockjs.route.RawWebSocketTransport")
    loop = asyncio.get_event_loop()
    ws.return_value.process.return_value = loop.create_future()
    ws.return_value.process.return_value.set_result(web.HTTPOk())

    route = make_route()
    request = make_request("GET", "/sm/", headers=CIMultiDict({}))
    res = await route.websocket(request)

    assert isinstance(res, web.HTTPOk)
    assert ws.called
    assert ws.return_value.process.called


async def _test_raw_websocket_fail(make_route, make_request):
    route = make_route()
    request = make_request("GET", "/sm/")
    res = await route.websocket(request)
    assert not isinstance(res, web.HTTPNotFound)


@pytest.mark.parametrize(
    ('url', 'method'),
    [
        ('/sockjs', "GET"),
        ('/sockjs/', "GET"),
        ('/sockjs/info', "GET"),
    ] + [
        (f'/sockjs/serv1/234/{transport}', method)
        for transport in transport_handlers.keys()
        for method in ALL_METH_WO_OPTIONS
    ] + [
        ('/sockjs/websocket', "GET"),
        ('/sockjs/iframe.html', "GET"),
        ('/sockjs/iframe12.html', "GET"),
    ]
)
async def test_cors_preflight(test_client: TestClient, url, method):
    origin = "http://my_example.com"
    headers = {
        "HOST": "server.example.com",
        "ACCESS-CONTROL-REQUEST-METHOD": method,
        "ACCESS-CONTROL-REQUEST-HEADERS": "origin, x-requested-with",
        "ORIGIN": origin,
    }

    response = await test_client.options(url, headers=headers)
    assert response.status in (200, 204)

    headers = response.headers
    assert dict(headers) == D({
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": method,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Max-Age": "31536000"
    })
