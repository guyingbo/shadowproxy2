import asyncio

from .. import app
from .base import InboundBase, OutboundBase


class TCPInbound(asyncio.Protocol, InboundBase):
    def __init__(self, ctx):
        self.ctx = ctx
        self.parser = ctx.create_server_parser()
        self.task = asyncio.create_task(ctx.run_proxy(self))
        self.task.add_done_callback(ctx.get_task_callback(repr(self)))

    def connection_made(self, transport):
        self.transport = transport
        self.parser.set_transport(transport)

    def connection_lost(self, exc):
        self.task.cancel()
        if exc is not None and app.settings.verbose > 0:
            print(f"{self} connection lost:", exc)
        self.transport.close()

    def data_received(self, data):
        self.parser.data_received(data)

    def write(self, data):
        if not self.transport.is_closing():
            self.transport.write(data)

    def write_eof(self):
        if self.transport.can_write_eof():
            self.transport.write_eof()


class TCPOutbound(asyncio.Protocol, OutboundBase):
    def __init__(self, ctx, target_addr):
        self.ctx = ctx
        self.target_addr = target_addr

    def connection_made(self, transport):
        self.transport = transport
        self.parser = self.ctx.create_client_parser(self.target_addr)
        if self.parser:
            self.parser.set_transport(transport)
            self.parser.data_received(b"")

    def connection_lost(self, exc):
        if exc is not None and app.settings.verbose > 0:
            print(f"{self} connection lost:", exc)
        self.transport.close()

    def data_received(self, data):
        if self.parser:
            self.parser.data_received(data)

    def write(self, data):
        if not self.transport.is_closing():
            self.transport.write(data)

    def write_eof(self):
        if self.transport.can_write_eof():
            self.transport.write_eof()
