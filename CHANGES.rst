=======
CHANGES
=======

0.13.0 (2024-06-13)
-------------------

- Added argument ``cors_config`` into function ``add_endpoint()``
  to support of CORS settings from ``aiohttp_cors``.
- Added arguments ``heartbeat_delay`` and ``disconnect_delay``
  into function ``add_endpoint()``.
- Function ``add_endpoint()`` now returns all registered routes.
- Replaced returning instances of error HTTP responses
  on raising its as exceptions.
- Changed name of some routes.
- Heartbeat task moved from ``SessionManager`` into ``Session``.
- Methods ``_acquire`` and ``_release`` of ``Sessions`` renamed into
  ``acquire`` and ``release``.
- Added processing of ``ConnectionError`` in ``StreamingTransport``.
- Changed arguments of handler function. Now handler function must be defined
  like ``async def handler(manager, session, msg):``
- Constants:

  - FRAME_OPEN
  - FRAME_CLOSE
  - FRAME_MESSAGE
  - FRAME_MESSAGE_BLOB
  - FRAME_HEARTBEAT

  replaced by ``Frame`` enums with corresponding values.
- Constants:

  - MSG_OPEN
  - MSG_MESSAGE
  - MSG_CLOSE
  - MSG_CLOSED

  replaced by ``MsgType`` enums with corresponding values.
- Constants:

  - STATE_NEW
  - STATE_OPEN
  - STATE_CLOSING
  - STATE_CLOSED

  replaced by ``SessionState`` enums with corresponding values.


0.12.0 (2022-02-08)
-------------------

- **Breaking change:** Removed argument ``timeout`` from ``Session.__init__()``
  and ``SessionManager.__init__()``.
- **Breaking change:** Argument ``heartbeat`` of ``SessionManager.__init__()``
  renamed into ``heartbeat_delay``.
- **Breaking change:** ``Session.registry`` renamed into ``Session.app``.
- **Breaking change:** Deleted method ``SessionManager.route_url()``.
- **Breaking change:** Dropped support of Python < 3.7
- Fixed processing of heartbeats and a session expiration.
- Fixed ping-pong based heartbeats for web-socket connections.
- Added arguments ``heartbeat_delay`` and ``disconnect_delay`` into
  ``Session.__init__()``.
- Added argument ``disconnect_delay`` into ``SessionManager.__init__()``.

0.11.0 (2020-10-22)
-------------------

- **Breaking change:** Added into the WebSocketTransport the ability
  to process multi messages from client (#383).
- Added into WebSocketTransport ignoring of empty frames received
  from client. (#383).
- Added tick after dequeue so heartbeat keeps session live (#265).
- Fix race condition during iteration over sessions (#217).
- Support Python 3.8.
- Fixed examples of using of SockJS server (#264).

0.10.0 (2019-10-20)
-------------------

- Sync with aiohttp 3.6 (#298)

0.9.1 (2018-12-04)
------------------

- Minor code styling cleanups

0.9.0 (2018-10-11)
------------------

- Support Python 3.7. The minimal available Python version is 3.5.3 (#240)

0.8.0 (2018-06-15)
------------------

- Fix heartbeat (#214)

0.7.1 (2018-03-05)
------------------

- Fix compatibility with aiohttp 3.0+ again.

0.7.0 (2018-02-25)
------------------

- Fixed compatibility with aiohttp 3.0+ (#169)

0.6 (2017-04-13)
----------------

- Fixed support for aiohttp 2.0+.

0.5 (2016-09-26)
----------------

- Mark SockJSRoute.handler and SockJSRoute.websocket as coroutines. #25

- Remove a check for "ORIGIN" header #12

- Process FRAME_MESSAGE_BLOB message type #12

0.4 (2016-02-04)
----------------

- Fixed lost event-loop argument in `sockjs.transports.websocket.WebSocketTransport`
- Fixed lost event-loop argument in `sockjs.transports.rawwebsocket.RawWebSocketTransport`
- Fixed RawRequestMessage. Add raw_header argument (aiohttp 0.21+)
- Fixed many warnings
- Fixed `sockjs.route` add_endpoint without name bug

0.3 (2015-08-07)
----------------

- Fixed calls of ``SessionManager.aquire()`` - was removed the unnecessary second argument.
- Fixed the incorrect argument in one call of ``cors_headers()``.
- Fixed many errors. The code is not perfect, but at least it was working as it should.

0.2 (2015-07-07)
----------------

- Fixed packaging

0.1.0 (2015-06-21)
------------------

- Initial release
