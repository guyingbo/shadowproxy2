import asyncio
from websockets import ConnectionClosedOK


class WebsocketWriter:
    def __init__(self, ws):
        self.ws = ws

    async def write(self, data):
        await self.ws.send(data)

    def can_write_eof(self):
        return False

    def is_closing(self):
        return self.ws.closed

    async def close(self):
        await self.ws.close()

    async def wait_closed(self):
        return await self.ws.wait_closed()


class WebsocketReader(asyncio.StreamReader):
    def __init__(self, ws):
        super().__init__()
        self.ws = ws

    def __repr__(self):
        return "<WebsocketReader>"

    async def _wait_for_data(self, func_name):
        """Wait until feed_data() or feed_eof() is called.

        If stream was paused, automatically resume it.
        """
        # StreamReader uses a future to link the protocol feed_data() method
        # to a read coroutine. Running two read coroutines at the same time
        # would have an unexpected behaviour. It would not possible to know
        # which coroutine would get the next data.
        if self._waiter is not None:
            raise RuntimeError(
                f"{func_name}() called while another coroutine is "
                f"already waiting for incoming data"
            )

        assert not self._eof, "_wait_for_data after EOF"

        # Waiting for data while paused will make deadlock, so prevent it.
        # This is essential for readexactly(n) for case when n > self._limit.
        if self._paused:
            self._paused = False
            self._transport.resume_reading()

        while not self._buffer and not self._eof:
            try:
                data = await self.ws.recv()
            except ConnectionClosedOK:
                self.feed_eof()
            else:
                self.feed_data(data)
