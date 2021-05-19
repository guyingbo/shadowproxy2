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

from ..aiobuffer import buffer as schema
from ..aiobuffer import socks5


class TrojanSchema(schema.BinarySchema):
    hex = schema.Bytes(56)
    crlf = schema.MustEqual(schema.Bytes(2), b"\r\n")
    cmd = schema.SizedIntEnum(schema.uint8, socks5.Cmd)
    addr = socks5.Addr
    crlf = schema.MustEqual(schema.Bytes(2), b"\r\n")
