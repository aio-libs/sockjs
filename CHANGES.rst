=======
CHANGES
=======

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
