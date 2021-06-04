import asyncio
from websockets.server import WebSocketServerProtocol
from websockets import ConnectionClosed


class WSInbound(WebSocketServerProtocol):
    @property
    def source_addr(self):
        return self.transport.get_extra_info("peername")


async def wait_recv(ws, reader):
    try:
        async for message in ws:
            reader.feed_data(message)
    except ConnectionClosed:
        reader.feed_eof()


class WebsocketWriter:
    def __init__(self, ws):
        self.ws = ws
        self.queue = asyncio.Queue()
        self.task = asyncio.create_task(self._run())

    def write(self, data):
        self.queue.put_nowait(data)

    async def _run(self):
        while True:
            data = await self.queue.get()
            if data is None:
                return
            await self.ws.send(data)

    def write_eof(self):
        self.queue.put_nowait(None)

    def can_write_eof(self):
        return True

    def is_closing(self):
        return False

    def close(self):
        self.write_eof()

    async def wait_closed(self):
        await self.task
