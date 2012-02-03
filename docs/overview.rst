Pyramid SockJS
==============

Overview
--------

Gevent-based SockJS integration for Pyramid. SockJS interface is 
implemented as pyramid route. It runs inside wsgi app rather than wsgi server.
It's possible to create any number of different sockjs routes, ie 
`/__sockjs__/*` or `/mycustom-sockjs/*`. also you can provide different
session implementation and management for each of sockjs routes.

Gevent based server is required for ``pyramid_sockjs``. 
For example ``gunicorn`` with gevent worker. ``pyramid_sockjs`` provides
simple paster server runner:

.. code-block:: text
   :linenos:

   [server:main]
   use = egg:pyramid_sockjs#server
   host = 0.0.0.0
   port = 8080

Example of sockjs route:

.. code-block:: python

   def main(global_settings, **settings):
       config = Configurator(settings=settings)
       config.add_sockjs_route()

       return config.make_wsgi_app()

By default :py:func:`add_sockjs_route` directive creates sockjs route
with empty name and prefix ``/__sockjs__``, so js client code should look like:


.. code-block:: javascript

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


All interactions between client and server happen through `Sessions`.
Its possible to override default session with custom implementation.
Default session is very stupid, its even not possible to receive 
client messages, so in most cases it is required to replace session.
Let's implement `echo` session as example:

.. code-block:: python

  from pyramid_sockjs.session import Session

  class EchoSession(Session):

      def on_open(self):
          self.send('Hello')
          self.manager.broadcast("Someone joined.")

      def on_message(self, message):
          self.send(message)

      def on_close(self):
          self.manager.broadcast("Someone left.")

To use custom session implementation pass it to :py:func:`add_sockjs_route`
directive:

.. code-block:: python

   def main(global_settings, **settings):
       config = Configurator(settings=settings)

       config.add_sockjs_route(session=EchoSession)

       return config.make_wsgi_app()


Sessions are managed by ``SessionManager``, each sockjs route has separate
session manager. Session manage is addressed by same name as sockjs route.
To get session manager use :py:func:`get_sockjs_manager`
request function.

.. code-block:: python

   def main(...):
       ...
       config.add_sockjs_route('chat-service')
       ...
       config.add_route('broadcast', '/broadcast')
       ...
       return config.make_wsgi_app()


   @view_config(route_name='broadcast', renderer='string')
   def send_message(request):
       message = request.GET.get('message')
       if message:
          manager = request.get_sockjs_manager('chat-service')
	  for session in manager.active_session():
              session.send(message)

       return 'Message has been sent' 


To use custom ``SessionManager`` pass it as `session_manager=` argument
to :py:func:`add_sockjs_route` configurator directive. 
Check :py:class:`pyramid_sockjs.Session` 
and :py:class:`pyramid_sockjs.SessionManager` api for 
detailed description.


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

pyramid_sockjs is offered under the BSD license.
