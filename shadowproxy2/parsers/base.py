class NullParser:
    def set_transport(self, transport):
        self.transport = transport

    def write(self, data):
        if not self.transport.is_closing():
            self.transport.write(data)

    def write_eof(self):
        if self.transport.can_write_eof():
            self.transport.write_eof()

    def relay(self, peer_parser):
        if hasattr(self, "buffer"):
            data = self.buffer.read_all()
            if data:
                peer_parser.write(data)
            self.buffer.push = peer_parser.write
        else:
            self.push = peer_parser.write
        self.push_eof = peer_parser.write_eof

    def push(self, data):
        if hasattr(self, "buffer"):
            self.buffer.push(data)

    def push_eof(self):
        if hasattr(self, "buffer"):
            self.buffer.push_eof()

    def close(self):
        if hasattr(self, "buffer"):
            self.buffer.close()

    async def init_client(self, target_addr):
        return