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

    def eof_received(self):
        self.task.cancel()
        self.transport.close()

    def data_received(self, data):
        self.parser.send(data)

    def send(self, data):
        self.transport.write(data)


class TCPEgress(asyncio.Protocol):
    def __init__(self, ctx, target_addr):
        self.ctx = ctx
        self.target_addr = target_addr

    def connection_made(self, transport):
        self.transport = transport
        self.parser = self.ctx.create_client_parser(self.target_addr)
        if self.parser:
            self.parser.set_transport(transport)
            self.parser.send(b"")

    def eof_received(self):
        self.transport.close()

    def send(self, data):
        self.transport.write(data)

    def data_received(self, data):
        if self.parser:
            self.parser.send(data)
