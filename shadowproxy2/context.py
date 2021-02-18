import asyncio
import ssl
from functools import partial

from aioquic import asyncio as aio
from aioquic.quic.configuration import QuicConfiguration

from iofree.parser import AsyncioParser

from .parsers import socks4, socks5
from .transport.quic import QuicIngress, QuicEgress
from .transport.tcp import TCPIngress, TCPEgress
from .config import config


class NullParser:
    def set_transport(self, transport):
        self.transport = transport


class ProxyContext:
    def __init__(self, ingress_ns, egress_ns):
        self.ingress_ns = ingress_ns
        self.egress_ns = egress_ns
        self.quic_egress = None

    def create_server_parser(self):
        generator = getattr(self, f"{self.ingress_ns.proxy}_server")()
        return AsyncioParser(generator)

    def socks5_server(self):
        ns = self.ingress_ns
        return socks5.server(ns.username, ns.password)

    def socks4_server(self):
        return socks4.server()

    def create_client_parser(self, target_addr):
        if self.egress_ns is None:
            # return NullParser()
            return None
        generator = getattr(self, f"{self.egress_ns.proxy}_client")(target_addr)
        return AsyncioParser(generator)

    def socks5_client(self, target_addr):
        ns = self.egress_ns
        return socks5.client(ns.username, ns.password, *target_addr)

    def socks4_client(self, target_addr):
        return socks4.client(*target_addr)

    async def create_server(self):
        return await getattr(self, f"create_{self.ingress_ns.transport}_server")()

    async def create_tcp_server(self):
        loop = asyncio.get_running_loop()
        return await loop.create_server(
            lambda: TCPIngress(self),
            self.ingress_ns.host,
            self.ingress_ns.port,
        )

    async def create_quic_server(self):
        configuration = QuicConfiguration(is_client=False)
        configuration.load_cert_chain(
            config.cert_chain,
            keyfile=config.key_file,
        )
        return await aio.serve(
            self.ingress_ns.host,
            self.ingress_ns.port,
            configuration=configuration,
            create_protocol=partial(
                QuicIngress,
                ctx=self,
            ),
        )

    async def create_client(self, target_addr):
        if self.egress_ns is None:
            return await self.create_tcp_client(target_addr)
        func = getattr(self, f"create_{self.egress_ns.transport}_client")
        return await func(target_addr)

    async def create_tcp_client(self, target_addr):
        loop = asyncio.get_running_loop()
        if self.egress_ns:
            host = self.egress_ns.host
            port = self.egress_ns.port
        else:
            host, port = target_addr
        _, egress_stream = await loop.create_connection(
            lambda: TCPEgress(self, target_addr), host, port
        )
        return egress_stream

    async def create_quic_client(self, target_addr):
        if self.quic_egress is None:
            configuration = QuicConfiguration()
            configuration.load_verify_locations(config.ca_cert)
            configuration.verify_mode = ssl.CERT_NONE

            # important: The async context manager must be hold here(reference count > 0), otherwise quic connection will be closed.
            self.quic_egress_acm = aio.connect(
                self.egress_ns.host,
                self.egress_ns.port,
                create_protocol=partial(QuicEgress, ctx=self),
                configuration=configuration,
            )
            self.quic_egress = await self.quic_egress_acm.__aenter__()
            await self.quic_egress.wait_connected()
        return self.quic_egress.create_stream(target_addr)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type=None, exc_value=None, tb=None):
        if hasattr(self, "quic_egress_acm"):
            await self.quic_egress_acm.__aexit__(exc_type, exc_value, tb)

    async def run_proxy(self, ingress_stream):
        request = await ingress_stream.parser.responses.get()
        target_addr = (request.addr.host, request.addr.port)
        egress_stream = await self.create_client(target_addr)
        ingress_stream.parser.send_event(0)
        if egress_stream.parser:
            await egress_stream.parser.responses.get()
        egress_stream.data_received = ingress_stream.write
        egress_stream.eof_received = ingress_stream.close
        data = ingress_stream.parser.readall()
        if data:
            egress_stream.write(data)
        ingress_stream.data_received = egress_stream.write
        ingress_stream.eof_received = egress_stream.close
