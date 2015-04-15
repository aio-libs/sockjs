import asyncio
from aiohttp import errors

from ..exceptions import SessionIsAcquired, SessionIsClosed
from ..protocol import close_frame, ENCODING
from ..protocol import STATE_CLOSING, STATE_CLOSED, FRAME_CLOSE, FRAME_MESSAGE


class Transport:

    def __init__(self, manager, session, request):
        self.manager = manager
        self.session = session
        self.request = request
        self.loop = request.app.loop


class StreamingTransport(Transport):

    timeout = None
    maxsize = 131072  # 128K bytes

    def __init__(self, manager, session, request):
        super().__init__(manager, session, request)

        self.size = 0
        self.response = None

    def send(self, text):
        blob = (text + '\n').encode(ENCODING)
        self.response.write(blob)

        self.size += len(blob)
        if self.size > self.maxsize:
            return True
        else:
            return False

    @asyncio.coroutine
    def handle_session(self):
        assert self.response is None, 'Response is not specified.'

        # session was interrupted
        if self.session.interrupted:
            self.send(close_frame(1002, 'Connection interrupted'))

        # session is closing or closed
        elif self.session.state in (STATE_CLOSING, STATE_CLOSED):
            yield from self.session._remote_closed()
            self.send(close_frame(3000, 'Go away!'))

        else:
            # acquire session
            try:
                yield from self.manager.acquire(self.session, self)
            except SessionIsAcquired:
                self.send(close_frame(2010, 'Another connection still open'))
            else:
                try:
                    while True:
                        if self.timeout:
                            try:
                                frame, text = yield from asyncio.wait_for(
                                    self.session._wait(),
                                    timeout=self.timeout, loop=self.loop)
                            except TimeoutError:
                                frame, text = FRAME_MESSAGE, 'a[]'
                        else:
                            frame, text = yield from self.session._wait()

                        if frame == FRAME_CLOSE:
                            yield from self.session._remote_closed()
                            self.send(text)
                            return
                        else:
                            stop = self.send(text)
                            if stop:
                                break
                except asyncio.CancelledError:
                    yield from self.session._remote_close(
                        exc=errors.ClientDisconnectedError)
                    yield from self.session._remote_closed()
                    raise
                except SessionIsClosed:
                    pass
                finally:
                    yield from self.manager.release(self.session)
