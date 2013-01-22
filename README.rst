Experimental SockJS server based on Tulip (PEP 3156)
====================================================

`pyramid_sockjs2` is a experimental `SockJS <http://sockjs.org>`_ server
based on `tulip <http://code.google.com/p/tulip/>`_ 
`PEP 3156 <http://www.python.org/dev/peps/pep-3156/>`_ async io module.

`pyramid_sockjs` is a `SockJS <http://sockjs.org>`_ integration for 
`Pyramid <http://www.pylonsproject.org/>`_.  SockJS interface is implemented as a 
`pyramid route <http://pyramid.readthedocs.org/en/latest/narr/urldispatch.html>`_. pyramid_sockjs runs inside 
a WSGI application rather than WSGI server.  This means all of your previous WSGI/Pyramid experience will be
relevant. Its possible to create any number of different sockjs routes, ie 
`/__sockjs__/*` or `/mycustom-sockjs/*`. You can provide different session implementation 
and management for each sockjs route.

Simple tulip based wsgi server is required::

   [server:main]
   use = egg:pyramid_sockjs#server
   host = 0.0.0.0
   port = 8080

Example of sockjs route::

   def main(global_settings, **settings):
       config = Configurator(settings=settings)
       config.add_sockjs_route(prefix='/__sockjs__')

       return config.make_wsgi_app()


Client side code::

  <script src="http://cdn.sockjs.org/sockjs-0.3.4.min.js"></script>
  <script>
      var sock = new SockJS('http://localhost:8080/__sockjs__');

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

.. image :: https://secure.travis-ci.org/fafhrd91/pyramid_sockjs.png
  :target:  https://secure.travis-ci.org/fafhrd91/pyramid_sockjs


Installation
------------

1. Install virtualenv::

    $ wget https://raw.github.com/pypa/virtualenv/master/virtualenv.py
    $ python3.3 ./virtualenv.py --no-site-packages sockjs

2. Install tulip::

    $ hg clone https://code.google.com/p/tulip/
    $ cd tulip
    $ ../sockjs/bin/python setup.py develop

3. Clone pyramid_sockjs from github and then install::

    $ git clone https://github.com/fafhrd91/pyramid_sockjs2.git
    $ cd pyramid_sockjs2
    $ ../sockjs/bin/python setup.py develop

To run chat example use following command::

    $ ./sockjs/bin/python ./pyramid_sockjs2/examples/chat.py


Supported transports
--------------------

* websocket (`hixie-76 <http://tools.ietf.org/html/draft-hixie-thewebsocketprotocol-76>`_
  and `hybi-10 <http://tools.ietf.org/html/draft-ietf-hybi-thewebsocketprotocol-10>`_)
* `xhr-streaming <https://secure.wikimedia.org/wikipedia/en/wiki/XMLHttpRequest#Cross-domain_requests>`_
* `xhr-polling <https://secure.wikimedia.org/wikipedia/en/wiki/XMLHttpRequest#Cross-domain_requests>`_
* `iframe-xhr-polling <https://developer.mozilla.org/en/DOM/window.postMessage>`_
* iframe-eventsource (`EventSource <http://dev.w3.org/html5/eventsource/>`_ used from an 
  `iframe via postMessage <https://developer.mozilla.org/en/DOM/window.postMessage>`_)
* iframe-htmlfile (`HtmlFile <http://cometdaily.com/2007/11/18/ie-activexhtmlfile-transport-part-ii/>`_
  used from an `iframe via postMessage <https://developer.mozilla.org/en/DOM/window.postMessage>`_.)
* `jsonp-polling <https://secure.wikimedia.org/wikipedia/en/wiki/JSONP>`_


Limitations
-----------

- Pyramid sockjs does not support multple websocket session with same session id.


Requirements
------------

- Python 3.3

- `virtualenv <http://pypi.python.org/pypi/virtualenv>`_


Examples
--------

You can find several `examples` in the pyramid_sockjs2 repository at github.

https://github.com/fafhrd91/pyramid_sockjs2/tree/master/examples

License
-------

pyramid_sockjs is offered under the MIT license.
