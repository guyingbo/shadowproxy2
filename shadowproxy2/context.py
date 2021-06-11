import asyncio
import contextlib
import ssl
import traceback
from contextvars import ContextVar
from functools import cached_property

import click
import websockets
from aioquic import asyncio as aio
from aioquic.asyncio.protocol import QuicStreamAdapter
from aioquic.quic.configuration import QuicConfiguration

from . import app
from .ciphers import ChaCha20IETFPoly1305
from .parsers import aead, http, socks4, socks5
from .parsers.base import NullParser
from .transport.ws import WebsocketWriter, wait_recv
from .throttle import Throttle

QuicStreamAdapter.close = lambda self: None
QuicStreamAdapter.get_extra_info = (
    lambda self, name, default=None: self.protocol._transport.get_extra_info(name)
)
source_addr_var = ContextVar("source_addr", default=("", 0))
inbound_addr_var = ContextVar("inbound_addr", default=("", 0))
outbound_addr_var = ContextVar("outbound_addr", default=("", 0))
remote_addr_var = ContextVar("remote_addr", default=("", 0))
target_addr_var = ContextVar("target_addr", default=("", 0))


class ProxyContext:
    stack: contextlib.AsyncExitStack

    def __init__(self, inbound_ns, outbound_ns):
        self.inbound_ns = inbound_ns
        self.outbound_ns = outbound_ns
        self.quic_outbound = None

    @cached_property
    def quic_client_lock(self):
        return asyncio.Lock()

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
            if self.inbound_ns.username is None:
                return aead.PlainParser()
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
            if self.outbound_ns.username is None:
                return aead.PlainParser()
            return aead.AEADParser(self.outbound_cipher)
        elif proxy == "http":
            ns = self.outbound_ns
            return http.HTTPParser(ns.username, ns.password)
        else:
            raise Exception(f"Unknown proxy type: {proxy}")

    async def create_server(self):
        return await getattr(self, f"create_{self.inbound_ns.transport}_server")()

    async def create_tcp_server(self):
        if self.inbound_ns.transport == "tls":
            sslcontext = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            sslcontext.load_cert_chain(
                str(app.settings.cert_chain), str(app.settings.key_file)
            )
        else:
            sslcontext = None
        server = await asyncio.start_server(
            self.tcp_handler,
            self.inbound_ns.host,
            self.inbound_ns.port,
            reuse_port=True,
            ssl=sslcontext,
        )
        return await self.stack.enter_async_context(server)

    create_tls_server = create_tcp_server

    def get_upload_throttle(self):
        throttle = None
        if self.inbound_ns.ul:
            throttle = Throttle(self.inbound_ns.ul * 1024)
        return throttle

    def get_download_throttle(self):
        throttle = None
        if self.inbound_ns.dl:
            throttle = Throttle(self.inbound_ns.dl * 1024)
        return throttle

    async def tcp_handler(self, reader, writer):
        try:
            source_addr_var.set(writer.get_extra_info("peername"))
            inbound_addr_var.set(writer.get_extra_info("sockname"))
            parser = self.create_server_parser()
            parser.set_rw(reader, writer, self.get_upload_throttle())
            remote_parser = await parser.server(self)
            self.create_task(parser.relay(remote_parser))
            self.create_task(remote_parser.relay(parser))
        except Exception as e:
            if app.settings.verbose > 0:
                click.secho(f"{self.get_route()} {e}", fg="yellow")
            await parser.close()

    async def ws_handler(self, ws, path):
        try:
            source_addr_var.set(ws.remote_address)
            inbound_addr_var.set(ws.local_address)
            parser = self.create_server_parser()
            parser.set_rw(None, WebsocketWriter(ws), self.get_upload_throttle())
            task = self.create_task(wait_recv(ws, parser.reader))
            remote_parser = await parser.server(self)
            self.create_task(parser.relay(remote_parser))
            self.create_task(remote_parser.relay(parser))
            await task
        except Exception as e:
            if app.settings.verbose > 0:
                click.secho(f"{self.get_route()} {e}", fg="yellow")
            await parser.close()

    async def create_ws_server(self):
        if self.inbound_ns.transport == "wss":
            sslcontext = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            sslcontext.load_cert_chain(
                str(app.settings.cert_chain), str(app.settings.key_file)
            )
        else:
            sslcontext = None

        server = websockets.serve(
            self.ws_handler,
            self.inbound_ns.host,
            self.inbound_ns.port,
            ssl=sslcontext,
        )
        return await self.stack.enter_async_context(server)

    create_wss_server = create_ws_server

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
            stream_handler=lambda r, w: self.create_task(self.tcp_handler(r, w)),
        )

    async def create_client(self, target_addr):
        target_addr_var.set(target_addr)
        if target_addr[0] in app.settings.blacklist:
            raise Exception(f"{target_addr[0]} is blocked")
        if self.outbound_ns is None:
            transport = "tcp"
        else:
            transport = self.outbound_ns.transport
        func = getattr(self, f"create_{transport}_client")
        reader, writer = await func(target_addr)
        if not isinstance(writer, WebsocketWriter):
            remote_addr_var.set(writer.get_extra_info("peername"))
            outbound_addr_var.set(writer.get_extra_info("sockname"))
        parser = self.create_client_parser()
        parser.set_rw(reader, writer, self.get_download_throttle())
        if app.settings.verbose > 0:
            print(self.get_route())
        return parser

    def get_route(self):
        s = source_addr_var.get() or ("", 0)
        i = inbound_addr_var.get() or ("", 0)
        o = outbound_addr_var.get() or ("", 0)
        r = remote_addr_var.get() or ("", 0)
        t = target_addr_var.get() or ("", 0)
        return (
            f"{s[0]}:{s[1]} -> {i[0]}:{i[1]} -> "
            f"{o[0]}:{o[1]} -> {r[0]}:{r[1]}({t[0]}:{t[1]})"
        )

    async def create_tcp_client(self, target_addr):
        sslcontext = None
        if self.outbound_ns and self.outbound_ns.transport == "tls":
            sslcontext = True
            # sslcontext = ssl.create_default_context()
            # sslcontext.check_hostname = False
        if self.outbound_ns:
            host = self.outbound_ns.host
            port = self.outbound_ns.port
        else:
            host, port = target_addr
        for i in range(1, -1, -1):
            try:
                return await asyncio.open_connection(
                    host,
                    port,
                    ssl=sslcontext,
                )
            except OSError as e:
                if app.settings.verbose > 1:
                    click.secho(f"{e} retrying...")
                if i == 0:
                    raise

    create_tls_client = create_tcp_client

    async def create_ws_client(self, target_addr):
        transport = self.outbound_ns.transport
        host = self.outbound_ns.host
        port = self.outbound_ns.port
        path = self.outbound_ns.path or "/ws"
        uri = f"{transport}://{host}:{port}{path}"
        for i in range(1, -1, -1):
            try:
                ws = await websockets.connect(uri)
            except OSError as e:
                if app.settings.verbose > 1:
                    click.secho(f"{e} retrying...")
                if i == 0:
                    raise
            else:
                outbound_addr_var.set(ws.local_address)
                remote_addr_var.set(ws.remote_address)
                reader = asyncio.StreamReader()
                writer = WebsocketWriter(ws)
                self.create_task(wait_recv(ws, reader))
                return reader, writer

    create_wss_client = create_ws_client

    async def create_quic_client(self, target_addr):
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
                    configuration=configuration,
                )
                self.quic_outbound = await self.stack.enter_async_context(
                    quic_outbound_acm
                )
                await self.quic_outbound.wait_connected()
            return await self.quic_outbound.create_stream()

    def task_callback(self, task):
        try:
            exc = task.exception()
        except asyncio.CancelledError as e:
            if app.settings.verbose > 0:
                click.secho(f"{e}", fg="yellow")
            return
        if exc and app.settings.verbose > 0:
            click.secho(f"{self.get_route()} {exc}", fg="magenta")
            if app.settings.verbose > 1:
                traceback.print_tb(exc.__traceback__)

    def create_task(self, coro):
        task = asyncio.create_task(coro)
        task.add_done_callback(self.task_callback)
        return task
