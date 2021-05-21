class NullParser:
    def set_transport(self, transport):
        self.transport = transport

    def write(self, data):
        self.transport.write(data)

    def write_eof(self):
        if hasattr(self.transport, "is_closing") and not self.transport.is_closing():
            self.transport.write_eof()

    def relay(self, peer_parser):
        self.peer_parser = peer_parser
        if hasattr(self, "buffer"):
            data = self.buffer.read_all()
            if data:
                peer_parser.write(data)
            self.buffer.push = peer_parser.write
        else:
            self.push = peer_parser.write
        self.push_eof = peer_parser.write_eof
        self.close = peer_parser.transport.close
        if hasattr(peer_parser.transport, "pause_reading"):
            self.pause_writing = peer_parser.transport.pause_reading
            self.resume_writing = peer_parser.transport.resume_reading

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

    def pause_writing(self):
        if hasattr(self, "peer_parser"):
            self.peer_parser.transport.pause_reading()

    def resume_writing(self):
        if hasattr(self, "peer_parser"):
            self.peer_parser.transport.resume_reading()
