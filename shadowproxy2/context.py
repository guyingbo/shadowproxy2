import asyncio
import contextlib
import ssl
from functools import partial

from aioquic import asyncio as aio
from aioquic.quic.configuration import QuicConfiguration

from iofree.parser import AsyncioParser

from .config import config
from .parsers import socks4, socks5
from .transport.quic import QuicOutbound, QuicInbound
from .transport.tcp import TCPOutbound, TCPInbound


class ProxyContext:
    stack: contextlib.AsyncExitStack

    def __init__(self, inbound_ns, outbound_ns):
        self.inbound_ns = inbound_ns
        self.outbound_ns = outbound_ns
        self.quic_outbound = None
        self.quic_client_lock = asyncio.Lock()

    def create_server_parser(self):
        generator = getattr(self, f"{self.inbound_ns.proxy}_server")()
        return AsyncioParser(generator)

    def socks5_server(self):
        ns = self.inbound_ns
        return socks5.server(ns.username, ns.password)

    def socks4_server(self):
        return socks4.server()

    def create_client_parser(self, target_addr):
        if self.outbound_ns is None:
            return None
        generator = getattr(self, f"{self.outbound_ns.proxy}_client")(target_addr)
        return AsyncioParser(generator)

    def socks5_client(self, target_addr):
        ns = self.outbound_ns
        return socks5.client(ns.username, ns.password, *target_addr)

    def socks4_client(self, target_addr):
        return socks4.client(*target_addr)

    async def create_server(self):
        return await getattr(self, f"create_{self.inbound_ns.transport}_server")()

    async def create_tcp_server(self, tls=False):
        if tls:
            sslcontext = ssl.create_default_context()
            sslcontext.load_cert_chain(config.cert_chain, config.key_file)
        else:
            sslcontext = None
        loop = asyncio.get_running_loop()
        server = await loop.create_server(
            lambda: TCPInbound(self),
            self.inbound_ns.host,
            self.inbound_ns.port,
            ssl=sslcontext,
        )
        return await self.stack.enter_async_context(server)

    async def create_tls_server(self):
        return await self.create_tcp_server(tls=True)

    async def create_quic_server(self):
        configuration = QuicConfiguration(is_client=False)
        configuration.load_cert_chain(
            config.cert_chain,
            keyfile=config.key_file,
        )
        return await aio.serve(
            self.inbound_ns.host,
            self.inbound_ns.port,
            configuration=configuration,
            create_protocol=partial(
                QuicInbound,
                ctx=self,
            ),
        )

    async def create_client(self, target_addr):
        if self.outbound_ns is None:
            return await self.create_tcp_client(target_addr)
        func = getattr(self, f"create_{self.outbound_ns.transport}_client")
        return await func(target_addr)

    async def create_tcp_client(self, target_addr):
        loop = asyncio.get_running_loop()
        if self.outbound_ns:
            host = self.outbound_ns.host
            port = self.outbound_ns.port
        else:
            host, port = target_addr
        _, outbound_stream = await loop.create_connection(
            lambda: TCPOutbound(self, target_addr), host, port
        )
        return outbound_stream

    async def create_quic_client(self, target_addr):
        async with self.quic_client_lock:
            if self.quic_outbound is None:
                configuration = QuicConfiguration()
                configuration.load_verify_locations(config.ca_cert)
                configuration.verify_mode = ssl.CERT_NONE

                # important: The async context manager must be hold here(reference count > 0), otherwise quic connection will be closed.
                quic_outbound_acm = aio.connect(
                    self.outbound_ns.host,
                    self.outbound_ns.port,
                    create_protocol=partial(QuicOutbound, ctx=self),
                    configuration=configuration,
                )
                self.quic_outbound = await self.stack.enter_async_context(quic_outbound_acm)
                await self.quic_outbound.wait_connected()
        return self.quic_outbound.create_stream(target_addr)

    async def run_proxy(self, inbound_stream):
        request = await inbound_stream.parser.responses.get()
        target_addr = (request.addr.host, request.addr.port)
        outbound_stream = await self.create_client(target_addr)
        inbound_stream.parser.event_received(0)
        if outbound_stream.parser:
            await outbound_stream.parser.responses.get()
        outbound_stream.data_received = inbound_stream.write
        outbound_stream.eof_received = inbound_stream.write_eof
        data = inbound_stream.parser.readall()
        if data:
            outbound_stream.write(data)
        inbound_stream.data_received = outbound_stream.write
        inbound_stream.eof_received = outbound_stream.write_eof

    def get_task_callback(self, info="error"):
        def task_callback(task):
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                if config.verbose > 0:
                    print(info, "cancelled")
                return
            if exc and config.verbose > 0:
                print(info, ":", exc)

        return task_callback
