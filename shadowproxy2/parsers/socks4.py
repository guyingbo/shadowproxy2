import enum
import socket

import iofree
from iofree import schema


class Cmd(enum.IntEnum):
    connect = 1
    bind = 2


class Rep(enum.IntEnum):
    granted = 0x5A
    rejected = 0x5B
    un_reachable = 0x5C
    auth_failed = 0x5D


class ClientRequest(schema.BinarySchema):
    ver = schema.MustEqual(schema.uint8, 4)
    cmd = schema.SizedIntEnum(schema.uint8, Cmd)
    dst_port = schema.uint16be
    dst_ip = schema.Convert(
        schema.Bytes(4), encode=socket.inet_aton, decode=socket.inet_ntoa
    )
    user_id = schema.EndWith(b"\x00")


class Response(schema.BinarySchema):
    vn = schema.MustEqual(schema.Bytes(1), b"\x00")
    rep = schema.SizedIntEnum(schema.uint8, Rep)
    dst_port = schema.uint16be
    dst_ip = schema.Convert(
        schema.Bytes(4), encode=socket.inet_aton, decode=socket.inet_ntoa
    )


domain = schema.EndWith(b"\x00")


def server():
    parser = yield from iofree.get_parser()
    request = yield from ClientRequest.get_value()
    if request.dst_ip.startswith("0.0.0"):
        host = yield from domain.get_value()
        addr = (host, request.dst_port)
    else:
        addr = (request.dst_ip, request.dst_port)
    assert request.cmd is Cmd.connect
    parser.respond(addr)
    rep = yield from iofree.wait_event()
    parser.write(Response(..., Rep(rep), 0, "0.0.0.0").binary)


def client(target_host: str, target_port: int):
    parser = yield from iofree.get_parser()
    tail = b""
    try:
        request = ClientRequest(..., Cmd.connect, target_port, target_host, b"\x01\x01")
    except OSError:
        request = ClientRequest(..., Cmd.connect, target_port, "0.0.0.1", b"\x01\x01")
        tail = domain(target_host.encode())
    parser.write(request.binary + tail)
    response = yield from Response.get_value()
    assert response.rep is Rep.granted
    parser.respond(response)
