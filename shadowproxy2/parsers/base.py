from inspect import isawaitable

from ..aiobuffer.buffer import create_buffer


class NullParser:
    def set_rw(self, reader, writer):
        self.reader = create_buffer(reader)
        self.writer = writer

    async def init_client(self, target_addr):
        return

    async def relay(self, output_parser):
        try:
            while True:
                try:
                    data = await self.reader.read(1024)
                except Exception as e:
                    print(e)
                    data = None
                if not data:
                    if (
                        output_parser.writer.can_write_eof()
                        and not output_parser.writer.is_closing()
                    ):
                        output_parser.writer.write_eof()
                    if self.writer.is_closing():
                        await output_parser.close()
                    break
                await output_parser.write(data)
        except Exception:
            await self.close()
            raise

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
        r = self.writer.close()
        if isawaitable(r):
            return await r
        await self.writer.wait_closed()
        return r
