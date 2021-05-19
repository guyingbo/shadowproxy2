import asyncio

from .. import app
from .base import InboundBase, OutboundBase


class TCPInbound(asyncio.Protocol, InboundBase):
    def __init__(self, ctx):
        self.ctx = ctx
        self.parser = ctx.create_server_parser(self)
        self.task = asyncio.create_task(ctx.run_proxy(self))
        self.task.add_done_callback(ctx.get_task_callback(repr(self)))

    def connection_made(self, transport):
        self.transport = transport
        self.source_addr = transport.get_extra_info("peername")
        self.parser.set_transport(transport)

    def connection_lost(self, exc):
        # self.task.cancel()
        if exc is not None and app.settings.verbose > 0:
            print(f"{self} connection lost:", exc)
        self.parser.close()
        self.transport.close()

    def data_received(self, data):
        self.parser.push(data)

    def eof_received(self):
        self.parser.push_eof()


class TCPOutbound(asyncio.Protocol, OutboundBase):
    def __init__(self, ctx, target_addr):
        self.ctx = ctx
        self.target_addr = target_addr

    def connection_made(self, transport):
        self.transport = transport
        self.parser = self.ctx.create_client_parser()
        self.parser.set_transport(transport)

    def connection_lost(self, exc):
        if exc is not None and app.settings.verbose > 0:
            print(f"{self} connection lost:", exc)
        self.parser.close()
        self.transport.close()

    def data_received(self, data):
        self.parser.push(data)

    def eof_received(self):
        self.parser.push_eof()
