import asyncio


class TCPIngress(asyncio.Protocol):
    def __init__(self, ctx):
        self.ctx = ctx
        self.parser = ctx.create_server_parser()
        self.task = asyncio.create_task(ctx.run_proxy(self))

        def myprint(task):
            exc = task.exception()
            if exc:
                print("error:", exc)

        self.task.add_done_callback(myprint)

    def connection_made(self, transport):
        self.transport = transport
        self.parser.set_transport(transport)

    def data_received(self, data):
        self.parser.data_received(data)

    def eof_received(self):
        # self.transport.close()
        self.parser.eof_received()

    def write(self, data):
        self.transport.write(data)

    def close(self):
        self.transport.close()


class TCPEgress(asyncio.Protocol):
    def __init__(self, ctx, target_addr):
        self.ctx = ctx
        self.target_addr = target_addr

    def connection_made(self, transport):
        self.transport = transport
        self.parser = self.ctx.create_client_parser(self.target_addr)
        if self.parser:
            self.parser.set_transport(transport)
            self.parser.data_received(b"")

    def write(self, data):
        self.transport.write(data)

    def data_received(self, data):
        if self.parser:
            self.parser.data_received(data)

    def eof_received(self):
        # self.transport.close()
        if self.parser:
            self.parser.eof_received()

    def close(self):
        self.transport.close()
