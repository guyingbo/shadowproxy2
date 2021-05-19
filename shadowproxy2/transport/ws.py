from websockets import ConnectionClosed


async def wait_recv(ws, reader):
    try:
        async for message in ws:
            reader.feed_data(message)
    except ConnectionClosed:
        reader.feed_eof()


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
