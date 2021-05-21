import asyncio

import click

from .. import app


class TCPInbound(asyncio.Protocol):
    def __init__(self, ctx):
        self.ctx = ctx
        self.parser = ctx.create_server_parser()

    def __repr__(self):
        peer = sock = ""
        if hasattr(self, "transport"):
            peername = self.transport.get_extra_info("peername")
            sockname = self.transport.get_extra_info("sockname")
            if peername:
                peer = f"{peername[0]}:{peername[1]}"
            if sockname:
                sock = f"{sockname[0]}:{sockname[1]}"
        return f"{self.__class__.__name__}({peer} -> {sock})"

    def __str__(self):
        return repr(self)

    def pause_writing(self):
        self.parser.pause_writing()

    def resume_writing(self):
        self.parser.resume_writing()

    def connection_made(self, transport):
        self.transport = transport
        self.source_addr = transport.get_extra_info("peername")
        self.parser.set_transport(transport)
        self.task = asyncio.create_task(self.ctx.run_proxy(self))
        self.task.add_done_callback(self.ctx.get_task_callback(repr(self)))

    def connection_lost(self, exc):
        if exc is not None and app.settings.verbose > 0:
            click.secho(f"{self} connection lost: {exc}", fg="yellow")
        self.parser.close()

    def data_received(self, data):
        self.parser.push(data)

    def eof_received(self):
        self.parser.push_eof()


class TCPOutbound(asyncio.Protocol):
    def __init__(self, ctx, target_addr):
        self.ctx = ctx
        self.target_addr = target_addr
        self._waiter = asyncio.Future()

    def __repr__(self):
        peer = sock = ""
        if hasattr(self, "transport"):
            peername = self.transport.get_extra_info("peername")
            sockname = self.transport.get_extra_info("sockname")
            if peername:
                peer = f"{peername[0]}:{peername[1]}"
            if sockname:
                sock = f"{sockname[0]}:{sockname[1]}"
            if peername != self.target_addr:
                peer += f"({self.target_addr[0]}:{self.target_addr[1]})"
        return f"{self.__class__.__name__}({sock} -> {peer})"

    def __str__(self):
        return repr(self)

    def pause_writing(self):
        self.parser.pause_writing()

    def resume_writing(self):
        self.parser.resume_writing()

    async def wait_connected(self):
        return await self._waiter

    def connection_made(self, transport):
        self.transport = transport
        self.parser = self.ctx.create_client_parser()
        self.parser.set_transport(transport)
        self._waiter.set_result(None)

    def connection_lost(self, exc):
        if exc is not None and app.settings.verbose > 0:
            click.secho(f"{self} connection lost: {exc}", fg="yellow")
        self.parser.close()

    def data_received(self, data):
        self.parser.push(data)

    def eof_received(self):
        self.parser.push_eof()
