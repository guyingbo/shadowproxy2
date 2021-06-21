# +-----------------------+---------+----------------+---------+----------+
# | hex(SHA224(password)) |  CRLF   | Trojan Request |  CRLF   | Payload  |
# +-----------------------+---------+----------------+---------+----------+
# |          56           | X'0D0A' |    Variable    | X'0D0A' | Variable |
# +-----------------------+---------+----------------+---------+----------+
#
# where Trojan Request is a SOCKS5-like request:
#
# +-----+------+----------+----------+
# | CMD | ATYP | DST.ADDR | DST.PORT |
# +-----+------+----------+----------+
# |  1  |  1   | Variable |    2     |
# +-----+------+----------+----------+
#
# where:
#     o  CMD
#         o  CONNECT X'01'
#         o  UDP ASSOCIATE X'03'
#     o  ATYP address type of following address
#         o  IP V4 address: X'01'
#         o  DOMAINNAME: X'03'
#         o  IP V6 address: X'04'
#     o  DST.ADDR desired destination address
#     o  DST.PORT desired destination port in network octet order
#
# if the connection is UDP ASSOCIATE, then each UDP packet has the following format:
# +------+----------+----------+--------+---------+----------+
# | ATYP | DST.ADDR | DST.PORT | Length |  CRLF   | Payload  |
# +------+----------+----------+--------+---------+----------+
# |  1   | Variable |    2     |   2    | X'0D0A' | Variable |
# +------+----------+----------+--------+---------+----------+

from hashlib import sha224

from ..aiobuffer import buffer as schema
from ..aiobuffer import socks5
from .base import NullParser
from ..iofree.exceptions import ProtocolError


class TrojanSchema(schema.BinarySchema):
    hex = schema.Bytes(56)
    crlf0 = schema.MustEqual(schema.Bytes(2), b"\r\n")
    cmd = schema.SizedIntEnum(schema.u8, socks5.Cmd)
    addr = socks5.Addr
    crlf1 = schema.MustEqual(schema.Bytes(2), b"\r\n")


class TrojanParser(NullParser):
    def __init__(self, username: str = None, password: str = None):
        super().__init__()
        self.username = username
        self.password = password
        if self.username is None or self.password is None:
            self.rauth = b''
        else:
            self.rauth = f"{username}:{password}".encode()

    async def server(self, ctx):
        trojan = await self.reader.pull(TrojanSchema)
        addr = socks5.Addr(1, "0.0.0.0", 0)
        if self.rauth:
            if sha224(self.rauth).hexdigest().encode() != trojan.hex:
                await self._write(
                    socks5.Reply(..., socks5.Rep.not_allowed, ..., addr).binary
                )
                raise ProtocolError("auth method not allowed")

        if trojan.cmd is not socks5.Cmd.connect:
            raise ProtocolError(
                f"only support connect command now, got {socks5.Cmd.connect!r}"
            )
        target_addr = (trojan.addr.host, trojan.addr.port)
        remote_parser = await ctx.create_client(target_addr)
        await remote_parser.init_client(target_addr)
        return remote_parser

    async def init_client(self, target_addr):

        await self._write(
                TrojanSchema(
                    sha224(self.rauth or b'').hexdigest().encode(), ...,
                    socks5.Cmd.connect, socks5.Addr.from_tuple(target_addr), ...
            ).binary
        )
