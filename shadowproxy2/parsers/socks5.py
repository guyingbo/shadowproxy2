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
                await self._write(
                    socks5.Reply(..., socks5.Rep.not_allowed, ..., addr).binary
                )
                raise ProtocolError("auth method not allowed")
            await self._write(
                socks5.ServerSelection(..., socks5.AuthMethod.user_auth).binary
            )
            user_auth = await self.reader.pull(socks5.UsernameAuth)
            if (user_auth.username, user_auth.password) != auth:
                await self._write(
                    socks5.Reply(..., socks5.Rep.not_allowed, ..., addr).binary
                )
                raise ProtocolError("auth failed")
            await self._write(socks5.UsernameAuthReply(..., ...).binary)
        else:
            await self._write(
                socks5.ServerSelection(..., socks5.AuthMethod.no_auth).binary
            )
        request = await self.reader.pull(socks5.ClientRequest)
        if request.cmd is not socks5.Cmd.connect:
            raise ProtocolError(
                f"only support connect command now, got {socks5.Cmd.connect!r}"
            )
        target_addr = (request.addr.host, request.addr.port)
        remote_parser = await ctx.create_client(target_addr)
        await self._write(socks5.Reply(..., socks5.Rep(0), ..., addr).binary)
        await remote_parser.init_client(target_addr)
        return remote_parser

    async def init_client(self, target_addr):
        if self.username is None or self.password is None:
            auth = None
        else:
            auth = self.username.encode(), self.password.encode()
        await self._write(
            socks5.Handshake(
                ..., [socks5.AuthMethod.no_auth, socks5.AuthMethod.user_auth]
            ).binary
        )
        server_selection = await self.reader.pull(socks5.ServerSelection)
        if server_selection.method not in (
            socks5.AuthMethod.no_auth,
            socks5.AuthMethod.user_auth,
        ):
            raise ProtocolError("no method to choose")
        if auth and (server_selection.method is socks5.AuthMethod.user_auth):
            await self._write(socks5.UsernameAuth(..., *auth).binary)
            await self.reader.pull(socks5.UsernameAuthReply)
        await self._write(
            socks5.ClientRequest(
                ..., socks5.Cmd.connect, ..., socks5.Addr.from_tuple(target_addr)
            ).binary
        )
        reply = await self.reader.pull(socks5.Reply)
        if reply.rep is not socks5.Rep.succeeded:
            raise ProtocolError(f"bad reply: {reply}")
        return reply
