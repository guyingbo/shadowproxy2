import asyncio
from inspect import isawaitable

from ..aiobuffer.buffer import create_buffer


class NullParser:
    def set_rw(self, reader, writer, throttle=None):
        self.reader = create_buffer(reader)
        self.writer = writer
        if throttle:
            self._event = asyncio.Event()
            self._event.set()
            self.throttle = throttle
            self.read_func = self.read
        else:
            self.read_func = self.reader.read

    def __repr__(self):
        s = super().__repr__()
        return f"{s}(closing={self.writer.is_closing()})"

    async def read(self, nbytes):
        await self._event.wait()
        data = await self.reader.read(nbytes)
        self.throttle.consume(len(data), self._event)
        return data

    async def init_client(self, target_addr):
        return

    async def relay(self, output_parser):
        try:
            while True:
                try:
                    data = await self.read_func(4096)
                except Exception:
                    data = None
                if data:
                    await output_parser.write(data)
                    continue
                if (
                    output_parser.writer.can_write_eof()
                    and not output_parser.writer.is_closing()
                ):
                    output_parser.writer.write_eof()
                break
        finally:
            await output_parser.close()
            await self.close()

    async def write(self, data):
        return await self._write(data, drain=True)

    async def _write(self, data, drain=False):
        r = self.writer.write(data)
        if isawaitable(r):
            return await r
        if drain:
            await self.writer.drain()
        return r

    async def close(self):
        if self.writer.is_closing():
            return
        r = self.writer.close()
        if isawaitable(r):
            return await r
        await self.writer.wait_closed()
        return r
