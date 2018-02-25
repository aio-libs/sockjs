import aiohttp
import asyncio

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

    async def send(self, text):
        blob = (text + '\n').encode(ENCODING)
        await self.response.write(blob)

        self.size += len(blob)
        if self.size > self.maxsize:
            return True
        else:
            return False

    async def handle_session(self):
        assert self.response is not None, 'Response is not specified.'

        # session was interrupted
        if self.session.interrupted:
            await self.send(close_frame(1002, 'Connection interrupted'))

        # session is closing or closed
        elif self.session.state in (STATE_CLOSING, STATE_CLOSED):
            await self.session._remote_closed()
            await self.send(close_frame(3000, 'Go away!'))

        else:
            # acquire session
            try:
                await self.manager.acquire(self.session)
            except SessionIsAcquired:
                await self.send(
                    close_frame(2010, 'Another connection still open'))
            else:
                try:
                    while True:
                        if self.timeout:
                            try:
                                frame, text = await asyncio.wait_for(
                                    self.session._wait(),
                                    timeout=self.timeout, loop=self.loop)
                            except asyncio.futures.TimeoutError:
                                frame, text = FRAME_MESSAGE, 'a[]'
                        else:
                            frame, text = await self.session._wait()

                        if frame == FRAME_CLOSE:
                            await self.session._remote_closed()
                            await self.send(text)
                            return
                        else:
                            stop = await self.send(text)
                            if stop:
                                break
                except asyncio.CancelledError:
                    await self.session._remote_close(
                        exc=aiohttp.ClientConnectionError)
                    await self.session._remote_closed()
                    raise
                except SessionIsClosed:
                    pass
                finally:
                    await self.manager.release(self.session)
