import asyncio
import click
import contextlib
import ssl
import traceback
from functools import cached_property, partial

from aioquic import asyncio as aio
from aioquic.quic.configuration import QuicConfiguration

from . import app
from .ciphers import ChaCha20IETFPoly1305
from .parsers import aead, socks4, socks5, http
from .parsers.base import NullParser
from .throttle import ProtocolProxy, Throttle
from .transport.quic import QuicInbound, QuicOutbound
from .transport.tcp import TCPInbound, TCPOutbound


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

    def create_server_parser(self):
        proxy = self.inbound_ns.proxy
        if proxy == "socks5":
            ns = self.inbound_ns
            return socks5.Socks5Parser(ns.username, ns.password)
        elif proxy == "socks4":
            return socks4.Socks4Parser()
        elif proxy == "ss":
            return aead.AEADParser(self.inbound_cipher)
        elif proxy == "http":
            ns = self.inbound_ns
            return http.HTTPParser(ns.username, ns.password)
        else:
            raise Exception(f"Unknown proxy type: {proxy}")

    def create_client_parser(self):
        if self.outbound_ns is None:
            return NullParser()
        proxy = self.outbound_ns.proxy
        if proxy == "socks5":
            ns = self.outbound_ns
            return socks5.Socks5Parser(ns.username, ns.password)
        elif proxy == "socks4":
            return socks4.Socks4Parser()
        elif proxy == "ss":
            return aead.AEADParser(self.outbound_cipher)
        elif proxy == "http":
            ns = self.outbound_ns
            return http.HTTPParser(ns.username, ns.password)
        else:
            raise Exception(f"Unknown proxy type: {proxy}")

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
        server = await loop.create_server(
            lambda: self.create_inbound_proxy(TCPInbound(self)),
            self.inbound_ns.host,
            self.inbound_ns.port,
            reuse_port=True,
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
        for i in range(1, -1, -1):
            try:
                _, outbound_proxy = await loop.create_connection(
                    lambda: self.create_outbound_proxy(
                        TCPOutbound(self, target_addr), source_addr
                    ),
                    host,
                    port,
                )
            except OSError as e:
                if app.settings.verbose > 1:
                    click.secho(f"{e} retrying...")
                if i == 0:
                    raise
            else:
                await outbound_proxy.wait_connected()
                break
        return getattr(outbound_proxy, "protocol", outbound_proxy)

    async def create_quic_client(self, target_addr, source_addr):
        async with self.quic_client_lock:
            if self.quic_outbound is None:
                configuration = QuicConfiguration()
                configuration.load_verify_locations(str(app.settings.ca_cert))
                configuration.verify_mode = ssl.CERT_NONE

                # important: The async context manager must be hold here
                # (reference count > 0), otherwise quic connection will be closed.
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
        try:
            outbound_stream = await inbound_stream.parser.server(inbound_stream)
            if app.settings.verbose > 0:
                print("%-50s" % inbound_stream, "->", outbound_stream)
            try:
                await outbound_stream.parser.init_client(outbound_stream.target_addr)
            except Exception:
                outbound_stream.transport.close()
                raise
            inbound_stream.parser.relay(outbound_stream.parser)
            outbound_stream.parser.relay(inbound_stream.parser)
        except Exception:
            inbound_stream.transport.close()
            raise

    def get_task_callback(self, info="error"):
        def task_callback(task):
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                if app.settings.verbose > 0:
                    click.secho(f"{info} cancelled", fg="yellow")
                return
            if exc and app.settings.verbose > 0:
                click.secho(f"{info} : {exc}", fg="magenta")
                if app.settings.verbose > 1:
                    traceback.print_tb(exc.__traceback__)

        return task_callback
