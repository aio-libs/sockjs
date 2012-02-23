Pyramid SockJS
==============

Gevent-based SockJS integration for Pyramid. SockJS interface is 
implemented as pyramid route. It runs inside wsgi app rather than wsgi server.
Its possible to create any number of different sockjs routes, ie 
`/__sockjs__/*` or `/mycustom-sockjs/*`. also you can provide different
session implementation and management for each of sockjs routes.

Gevent based server is required for ``pyramid_sockjs``. 
For example ``gunicorn`` with gevent worker. ``pyramid_sockjs`` provides
simple gevent based paster server runner::

   [server:main]
   use = egg:pyramid_sockjs#server
   host = 0.0.0.0
   port = 8080

Example of sockjs route::

   def main(global_settings, **settings):
       config = Configurator(settings=settings)
       config.add_sockjs_route()

       return config.make_wsgi_app()


Client side code::

  <script src="http://cdn.sockjs.org/sockjs-0.2.min.js"></script>
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


Installation
------------

1. Install virtualenv::

    $ wget https://raw.github.com/pypa/virtualenv/master/virtualenv.py
    $ python2.7 ./virtualenv.py --no-site-packages sockjs

2. Install gevent 1.0b1::

    $ ./sockjs/bin/pip install http://gevent.googlecode.com/files/gevent-1.0b1.tar.gz

3. Clone pyramid_sockjs from github and then install::

    $ git clone git://github.com/fafhrd91/pyramid_sockjs.git
    $ cd pyramid_sockjs
    $ ../sockjs/bin/python setup.py develop


To run chat example use following command::

    $ ./sockjs/bin/python ./pyramid_sockjs/examples/chat.py



Supported transports
--------------------

* websocket
* xhr-streaming
* xhr-polling
* iframe-xhr-polling
* iframe-eventsource
* iframe-htmlfile
* jsonp-polling

Websocket protocol version hixie-75 and hixie-76 are not supported.


Requirements
------------

- Python 2.6/2.7

- virtualenv

- gevent 1.0b1

- gevent-websocket 0.3.0


Examples
--------

You can find them in the `examples` repository at github.

https://github.com/fafhrd91/pyramid_sockjs/tree/master/examples


License
-------

pyramid_sockjs is offered under the MIT license.
