from ..aiobuffer import socks5
from .base import NullParser


class ProtocolError(Exception):
    ...


class Socks5Parser(NullParser):
    def __init__(self, username: str = None, password: str = None):
        super().__init__()
        self.username = username
        self.password = password

    async def server(self, ctx):
        if self.username is None or self.password is None:
            auth = None
        else:
            auth = self.username.encode(), self.password.encode()
        handshake = await self.reader.pull(socks5.Handshake)
        addr = socks5.Addr(1, "0.0.0.0", 0)
        if auth:
            if socks5.AuthMethod.user_auth not in handshake.methods:
                self.writer.write(
                    socks5.Reply(..., socks5.Rep.not_allowed, ..., addr).binary
                )
                self.writer.close()
                raise ProtocolError("auth method not allowed")
            self.writer.write(
                socks5.ServerSelection(..., socks5.AuthMethod.user_auth).binary
            )
            user_auth = await self.reader.pull(socks5.UsernameAuth)
            if (user_auth.username, user_auth.password) != auth:
                self.writer.write(
                    socks5.Reply(..., socks5.Rep.not_allowed, ..., addr).binary
                )
                self.writer.close()
                raise ProtocolError("auth failed")
            self.writer.write(socks5.UsernameAuthReply(..., ...).binary)
        else:
            self.writer.write(
                socks5.ServerSelection(..., socks5.AuthMethod.no_auth).binary
            )
        request = await self.reader.pull(socks5.ClientRequest)
        if request.cmd is not socks5.Cmd.connect:
            raise ProtocolError(
                f"only support connect command now, got {socks5.Cmd.connect!r}"
            )
        target_addr = (request.addr.host, request.addr.port)
        remote_parser = await ctx.create_client(target_addr)
        self.writer.write(socks5.Reply(..., socks5.Rep(0), ..., addr).binary)
        await remote_parser.init_client(target_addr)
        return remote_parser

    async def init_client(self, target_addr):
        if self.username is None or self.password is None:
            auth = None
        else:
            auth = self.username.encode(), self.password.encode()
        self.writer.write(
            socks5.Handshake(
                ..., [socks5.AuthMethod.no_auth, socks5.AuthMethod.user_auth]
            ).binary
        )
        server_selection = await self.reader.pull(socks5.ServerSelection)
        if server_selection.method not in (
            socks5.AuthMethod.no_auth,
            socks5.AuthMethod.user_auth,
        ):
            self.writer.close()
            raise ProtocolError("no method to choose")
        if auth and (server_selection.method is socks5.AuthMethod.user_auth):
            self.writer.write(socks5.UsernameAuth(..., *auth).binary)
            await self.reader.pull(socks5.UsernameAuthReply)
        self.writer.write(
            socks5.ClientRequest(
                ..., socks5.Cmd.connect, ..., socks5.Addr.from_tuple(target_addr)
            ).binary
        )
        reply = await self.reader.pull(socks5.Reply)
        if reply.rep is not socks5.Rep.succeeded:
            self.writer.close()
            raise ProtocolError(f"bad reply: {reply}")
        return reply
