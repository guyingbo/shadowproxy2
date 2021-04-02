from .. import iofree
from ..iofree.contrib import socks5
from ..iofree.exceptions import ProtocolError


def server(username: str = None, password: str = None):
    if username is None or password is None:
        auth = None
    else:
        auth = username.encode(), password.encode()
    parser = yield from iofree.get_parser()
    handshake = yield from socks5.Handshake.get_value()
    addr = socks5.Addr(1, "0.0.0.0", 0)
    if auth:
        if socks5.AuthMethod.user_auth not in handshake.methods:
            parser.write(socks5.Reply(..., socks5.Rep.not_allowed, ..., addr).binary)
            parser.close()
            raise ProtocolError("auth method not allowed")
        parser.write(socks5.ServerSelection(..., socks5.AuthMethod.user_auth).binary)
        user_auth = yield from socks5.UsernameAuth.get_value()
        if (user_auth.username, user_auth.password) != auth:
            parser.write(socks5.Reply(..., socks5.Rep.not_allowed, ..., addr).binary)
            parser.close()
            raise ProtocolError("auth failed")
        parser.write(socks5.UsernameAuthReply(..., ...).binary)
    else:
        parser.write(socks5.ServerSelection(..., socks5.AuthMethod.no_auth).binary)
    request = yield from socks5.ClientRequest.get_value()
    if request.cmd is not socks5.Cmd.connect:
        raise ProtocolError(
            f"only support connect command now, got {socks5.Cmd.connect!r}"
        )
    parser.respond(request.addr)
    rep = yield from iofree.wait_event()
    parser.write(socks5.Reply(..., socks5.Rep(rep), ..., addr).binary)


def client(username: str, password: str, target_host: str, target_port: int):
    if username is None or password is None:
        auth = None
    else:
        auth = username.encode(), password.encode()
    target_addr = (target_host, target_port)
    parser = yield from iofree.get_parser()
    yield from iofree.wait()
    parser.write(
        socks5.Handshake(
            ..., [socks5.AuthMethod.no_auth, socks5.AuthMethod.user_auth]
        ).binary
    )
    server_selection = yield from socks5.ServerSelection.get_value()
    if server_selection.method not in (
        socks5.AuthMethod.no_auth,
        socks5.AuthMethod.user_auth,
    ):
        parser.close()
        raise ProtocolError("no method to choose")
    if auth and (server_selection.method is socks5.AuthMethod.user_auth):
        parser.write(socks5.UsernameAuth(..., *auth).binary)
        yield from socks5.UsernameAuthReply.get_value()
    parser.write(
        socks5.ClientRequest(
            ..., socks5.Cmd.connect, ..., socks5.Addr.from_tuple(target_addr)
        ).binary
    )
    reply = yield from socks5.Reply.get_value()
    if reply.rep is not socks5.Rep.succeeded:
        parser.close()
        raise ProtocolError(f"bad reply: {reply}")
    parser.respond(reply)
