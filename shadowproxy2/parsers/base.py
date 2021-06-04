from ..aiobuffer.buffer import create_buffer


class NullParser:
    def set_rw(self, reader, writer):
        self.reader = create_buffer(reader)
        self.writer = writer

    async def init_client(self, target_addr):
        return

    async def relay(self, output_parser):
        while True:
            try:
                data = await self.reader.read(1024)
            except Exception as e:
                print(e)
                data = None
            if not data:
                return
                if (
                    output_parser.writer.can_write_eof()
                    and not output_parser.writer.is_closing()
                ):
                    output_parser.writer.write_eof()
                output_parser.writer.close()
                try:
                    await output_parser.writer.wait_closed()
                except Exception as e:
                    print(e)
                break
            output_parser.write(data)

    def write(self, data):
        return self.writer.write(data)
