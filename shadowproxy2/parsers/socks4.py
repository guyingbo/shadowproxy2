import enum
import socket

from ..aiobuffer import buffer as schema
from .base import NullParser


class Cmd(enum.IntEnum):
    connect = 1
    bind = 2


class Rep(enum.IntEnum):
    granted = 0x5A
    rejected = 0x5B
    un_reachable = 0x5C
    auth_failed = 0x5D


class ClientRequest(schema.BinarySchema):
    ver = schema.MustEqual(schema.u8, 4)
    cmd = schema.SizedIntEnum(schema.u8, Cmd)
    dst_port = schema.u16be
    dst_ip = schema.Convert(
        schema.Bytes(4), encode=socket.inet_aton, decode=socket.inet_ntoa
    )
    user_id = schema.EndWith(b"\x00")


class Response(schema.BinarySchema):
    vn = schema.MustEqual(schema.Bytes(1), b"\x00")
    rep = schema.SizedIntEnum(schema.u8, Rep)
    dst_port = schema.u16be
    dst_ip = schema.Convert(
        schema.Bytes(4), encode=socket.inet_aton, decode=socket.inet_ntoa
    )


domain = schema.EndWith(b"\x00")


class Socks4Parser(NullParser):
    async def server(self, ctx):
        request = await self.reader.pull(ClientRequest)
        if request.dst_ip.startswith("0.0.0"):
            host = await self.reader.pull(domain)
            addr = (host, request.dst_port)
        else:
            addr = (request.dst_ip, request.dst_port)
        assert request.cmd is Cmd.connect
        remote_parser = await ctx.create_client(addr)
        await self._write(Response(..., Rep(0x5A), 0, "0.0.0.0").binary)
        await remote_parser.init_client(addr)
        return remote_parser

    async def init_client(self, target_addr):
        tail = b""
        target_host, target_port = target_addr
        try:
            request = ClientRequest(
                ..., Cmd.connect, target_port, target_host, b"\x01\x01"
            )
        except OSError:
            request = ClientRequest(
                ..., Cmd.connect, target_port, "0.0.0.1", b"\x01\x01"
            )
            tail = domain(target_host.encode())
        await self._write(request.binary + tail)
        response = await self.reader.pull(Response)
        assert response.rep is Rep.granted
        return response
