import asyncio
import contextlib
import ssl
from functools import cached_property, partial

from aioquic import asyncio as aio
from aioquic.quic.configuration import QuicConfiguration

from .iofree.parser import AsyncioParser

from . import app
from .ciphers import ChaCha20IETFPoly1305
from .parsers import aead, socks4, socks5
from .transport.aead import AEADInbound, AEADOutbound
from .transport.quic import QuicInbound, QuicOutbound
from .transport.tcp import TCPInbound, TCPOutbound
from .throttle import ProtocolProxy, Throttle


class ProxyContext:
    stack: contextlib.AsyncExitStack

    def __init__(self, inbound_ns, outbound_ns):
        self.inbound_ns = inbound_ns
        self.outbound_ns = outbound_ns
        self.quic_outbound = None
        self.quic_client_lock = asyncio.Lock()
        self.throttles = {}

    @cached_property
    def inbound_cipher(self):
        return ChaCha20IETFPoly1305(self.inbound_ns.password)

    @cached_property
    def outbound_cipher(self):
        return ChaCha20IETFPoly1305(self.outbound_ns.password)

    def create_inbound_parser(self):
        return aead.reader.parser(self.inbound_cipher)

    def create_outbound_parser(self):
        return aead.reader.parser(self.outbound_cipher)

    def create_server_parser(self):
        proxy = self.inbound_ns.proxy
        if proxy == "socks5":
            ns = self.inbound_ns
            generator = socks5.server(ns.username, ns.password)
        elif proxy == "socks4":
            generator = socks4.server()
        elif proxy == "ss":
            generator = aead.ss_server()
        else:
            raise Exception(f"Unknown proxy type: {proxy}")
        return AsyncioParser(generator)

    def create_client_parser(self, target_addr):
        if self.outbound_ns is None:
            return None
        proxy = self.outbound_ns.proxy
        if proxy == "socks5":
            ns = self.outbound_ns
            generator = socks5.client(ns.username, ns.password, *target_addr)
        elif proxy == "socks4":
            generator = socks4.client(*target_addr)
        elif proxy == "ss":
            generator = aead.ss_client(target_addr)
        else:
            raise Exception(f"Unknown proxy type: {proxy}")
        return AsyncioParser(generator)

    def create_inbound_proxy(self, inbound):
        if self.inbound_ns.ul:
            throttle = Throttle(self.inbound_ns.ul * 1024)
            return ProtocolProxy(inbound, throttle)
        return inbound

    def create_outbound_proxy(self, outbound, source_addr):
        if self.inbound_ns.dl:
            throttle = self.throttles.setdefault(
                source_addr[0], Throttle(self.inbound_ns.dl * 1024)
            )
            return ProtocolProxy(outbound, throttle)
        return outbound

    async def create_server(self):
        return await getattr(self, f"create_{self.inbound_ns.transport}_server")()

    async def create_tcp_server(self, tls=False):
        if tls:
            sslcontext = ssl.create_default_context()
            sslcontext.load_cert_chain(
                str(app.settings.cert_chain), str(app.settings.key_file)
            )
        else:
            sslcontext = None
        loop = asyncio.get_running_loop()
        Inbound = TCPInbound
        if self.inbound_ns.proxy == "ss":
            Inbound = AEADInbound
        server = await loop.create_server(
            lambda: self.create_inbound_proxy(Inbound(self)),
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
            str(app.settings.cert_chain),
            keyfile=str(app.settings.key_file),
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

    async def create_client(self, target_addr, source_addr):
        if self.outbound_ns is None:
            return await self.create_tcp_client(target_addr, source_addr)
        func = getattr(self, f"create_{self.outbound_ns.transport}_client")
        return await func(target_addr, source_addr)

    async def create_tcp_client(self, target_addr, source_addr):
        loop = asyncio.get_running_loop()
        if self.outbound_ns:
            host = self.outbound_ns.host
            port = self.outbound_ns.port
        else:
            host, port = target_addr
        Outbound = TCPOutbound
        if self.outbound_ns and self.outbound_ns.proxy == "ss":
            Outbound = AEADOutbound
        for i in range(1, -1, -1):
            try:
                _, outbound_proxy = await loop.create_connection(
                    lambda: self.create_outbound_proxy(
                        Outbound(self, target_addr), source_addr
                    ),
                    host,
                    port,
                )
            except OSError as e:
                if app.settings.verbose > 1:
                    print(e, "retrying...")
                if i == 0:
                    raise
            else:
                break
        return getattr(outbound_proxy, "protocol", outbound_proxy)

    async def create_quic_client(self, target_addr, source_addr):
        async with self.quic_client_lock:
            if self.quic_outbound is None:
                configuration = QuicConfiguration()
                configuration.load_verify_locations(str(app.settings.ca_cert))
                configuration.verify_mode = ssl.CERT_NONE

                # important: The async context manager must be hold here(reference count > 0), otherwise quic connection will be closed.
                quic_outbound_acm = aio.connect(
                    self.outbound_ns.host,
                    self.outbound_ns.port,
                    create_protocol=partial(QuicOutbound, ctx=self),
                    configuration=configuration,
                )
                self.quic_outbound = await self.stack.enter_async_context(
                    quic_outbound_acm
                )
                await self.quic_outbound.wait_connected()
        outbound_stream = self.quic_outbound.create_stream(target_addr)
        self.create_outbound_proxy(outbound_stream, source_addr)
        return outbound_stream

    async def run_proxy(self, inbound_stream):
        addr = await inbound_stream.parser.responses.get()
        target_addr = (addr.host, addr.port)
        outbound_stream = await self.create_client(
            target_addr, inbound_stream.source_addr
        )
        inbound_stream.parser.event_received(0)
        if app.settings.verbose > 0:
            print(inbound_stream, "->", outbound_stream)
        if outbound_stream.parser:
            await outbound_stream.parser.responses.get()
        if hasattr(outbound_stream, "data_callback"):
            outbound_stream.data_callback = inbound_stream.write
        else:
            outbound_stream.data_received = inbound_stream.write
        if hasattr(outbound_stream, "eof_callback"):
            outbound_stream.eof_callback = inbound_stream.write_eof
        else:
            outbound_stream.eof_received = inbound_stream.write_eof
        data = inbound_stream.parser.readall()
        if data:
            outbound_stream.write(data)
        if hasattr(inbound_stream, "data_callback"):
            inbound_stream.data_callback = outbound_stream.write
        else:
            inbound_stream.data_received = outbound_stream.write
        if hasattr(inbound_stream, "eof_callback"):
            inbound_stream.eof_callback = outbound_stream.write_eof
        else:
            inbound_stream.eof_received = outbound_stream.write_eof

    def get_task_callback(self, info="error"):
        def task_callback(task):
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                if app.settings.verbose > 0:
                    print(info, "cancelled")
                return
            if exc and app.settings.verbose > 0:
                print(info, ":", exc)

        return task_callback
