import asyncio

from ..config import config


class AEADInbound(asyncio.Protocol):
    def __init__(self, ctx):
        self.ctx = ctx
        self.aead_parser = ctx.create_inbound_parser()
        self.parser = ctx.create_server_parser()
        self.data_callback = self.parser.data_received
        self.eof_callback = self.parser.eof_received
        self.task = asyncio.create_task(ctx.run_proxy(self))
        self.task.add_done_callback(ctx.get_task_callback(repr(self)))

    def data_received(self, data):
        self.aead_parser.data_received(data)
        responses = self.aead_parser.responses
        while responses:
            payload = responses.popleft()
            self.data_callback(payload)

    def eof_received(self):
        self.eof_callback()

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        if exc is not None and config.verbose > 0:
            print(f"{self} connection lost:", exc)
        self.transport.close()

    def write(self, data):
        packet = b""
        if not hasattr(self, "encrypt"):
            packet, self.encrypt = self.ctx.inbound_cipher.make_encrypter()
        packet += self.encrypt(data)
        self.transport.write(packet)

    def write_eof(self):
        if self.transport.can_write_eof():
            self.transport.write_eof()


class AEADOutbound(asyncio.Protocol):
    def __init__(self, ctx, target_addr):
        self.ctx = ctx
        self.target_addr = target_addr
        self.parser = self.ctx.create_client_parser(target_addr)
        self.data_callback = self.parser.data_received
        self.eof_callback = self.parser.eof_received
        self.aead_parser = ctx.create_outbound_parser()

    def data_received(self, data):
        self.aead_parser.data_received(data)
        responses = self.aead_parser.responses
        while responses:
            payload = responses.popleft()
            self.data_callback(payload)

    def eof_received(self):
        self.eof_callback()

    def connection_made(self, transport):
        self.transport = transport
        self.parser.set_transport(self)
        self.parser.data_received(b"")

    def connection_lost(self, exc):
        if exc is not None and config.verbose > 0:
            print(f"{self} connection lost:", exc)
        self.transport.close()

    def write(self, data):
        packet = b""
        if not hasattr(self, "encrypt"):
            packet, self.encrypt = self.ctx.outbound_cipher.make_encrypter()
        packet += self.encrypt(data)
        self.transport.write(packet)

    def write_eof(self):
        if self.transport.can_write_eof():
            self.transport.write_eof()
