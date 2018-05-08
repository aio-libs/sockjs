SockJS server based on Asyncio (PEP 3156)
=========================================

.. image :: https://secure.travis-ci.org/aio-libs/sockjs.svg
  :target:  https://secure.travis-ci.org/aio-libs/sockjs

`sockjs` is a `SockJS <http://sockjs.org>`_ integration for
`aiohttp <https://github.com/aio-libs/aiohttp/>`_.  SockJS interface
is implemented as a `aiohttp` route. Its possible to create any number
of different sockjs routes, ie `/sockjs/*` or
`/mycustom-sockjs/*`. You can provide different session implementation
and management for each sockjs route.

Simple aiohttp web server is required::

   [server:main]
   use = egg:gunicorn#main
   host = 0.0.0.0
   port = 8080
   worker = aiohttp.worker.GunicornWebWorker


Example of sockjs route::

   def main(global_settings, **settings):
       app = web.Application(loop=loop)
       app.router.add_route('GET', '/', index)
       sockjs.add_endpoint(app, prefix='/sockjs', handler=chatSession)

       handler = app.make_handler()
       srv = loop.run_until_complete(
           loop.create_server(handler, '127.0.0.1', 8080))
       print("Server started at http://127.0.0.1:8080")
       try:
           loop.run_forever()
        except KeyboardInterrupt:
           srv.close()
           loop.run_until_complete(handler.finish_connections())


Client side code::

  <script src="//cdn.jsdelivr.net/sockjs/0.3.4/sockjs.min.js"></script>
  <script>
      var sock = new SockJS('http://localhost:8080/sockjs');

      sock.onopen = function() {
        console.log('open');
      };

      sock.onmessage = function(obj) {
        console.log(obj);
      };

      sock.onclose = function() {
        console.log('close');
      };
  </script>


Supported transports
--------------------

* websocket `hybi-10
  <http://tools.ietf.org/html/draft-ietf-hybi-thewebsocketprotocol-10>`_
* `xhr-streaming
  <https://secure.wikimedia.org/wikipedia/en/wiki/XMLHttpRequest#Cross-domain_requests>`_
* `xhr-polling
  <https://secure.wikimedia.org/wikipedia/en/wiki/XMLHttpRequest#Cross-domain_requests>`_
* `iframe-xhr-polling
  <https://developer.mozilla.org/en/DOM/window.postMessage>`_
* iframe-eventsource (`EventSource
  <http://dev.w3.org/html5/eventsource/>`_ used from an `iframe via
  postMessage
  <https://developer.mozilla.org/en/DOM/window.postMessage>`_)
* iframe-htmlfile (`HtmlFile
  <http://cometdaily.com/2007/11/18/ie-activexhtmlfile-transport-part-ii/>`_
  used from an *iframe via postMessage*.
* `jsonp-polling <https://secure.wikimedia.org/wikipedia/en/wiki/JSONP>`_


Requirements
------------

- Python 3.4

- gunicorn 19.2.0

- aiohttp https://github.com/aio-libs/aiohttp


Examples
--------

You can find several `examples` in the sockjs repository at github.

https://github.com/aio-libs/sockjs/tree/master/examples


License
-------

sockjs is offered under the Apache 2 license.
