import base64
import re
from urllib.parse import urlparse

from ..aiobuffer import buffer as schema
from .base import NullParser

HTTP_LINE = re.compile(b"([^ ]+) +(.+?) +(HTTP/[^ ]+)")
ABSOLUTE_PREFIX = re.compile(r"^(.*://)?[^/]*")


class ProtocolError(Exception):
    ...


class HTTPResponse(schema.BinarySchema):
    head = schema.EndWith(b"\r\n\r\n")

    def __post_init__(self):
        first_line, *header_lines = self.head.split(b"\r\n")
        self.ver, self.code, *status = first_line.split(None, 2)
        self.status = status[0] if status else b""
        self.header_lines = header_lines


class HTTPRequest(schema.BinarySchema):
    head = schema.EndWith(b"\r\n\r\n")

    def __post_init__(self):
        first_line, *header_lines = self.head.split(b"\r\n")
        self.method, self.path, self.ver = HTTP_LINE.fullmatch(first_line).groups()
        self.headers = dict([line.split(b": ", 1) for line in header_lines])

    def build_send_data(self, username: str, password: str):
        if username is None or password is None:
            auth = None
        else:
            auth = username.encode(), password.encode()
        headers_list = [
            b"%s: %s" % (k, v)
            for k, v in self.headers.items()
            if not k.startswith(b"Proxy-")
        ]
        headers_list.append(b"Proxy-Connection: Keep-Alive")
        if auth:
            headers_list.append(
                b"Proxy-Authorization: Basic %s" % base64.b64encode(b":".join(auth))
            )
        lines = b"\r\n".join(headers_list)
        path = ABSOLUTE_PREFIX.sub("", self.path)
        return b"%s %s %s\r\n%s\r\n\r\n" % (
            self.method,
            path,
            self.ver,
            lines,
        )


class HTTPParser(NullParser):
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        if username is None or password is None:
            self.auth = None
        else:
            self.auth = self.username.encode(), self.password.encode()

    async def server(self, ctx):
        request = await self.reader.pull(HTTPRequest)
        if self.auth:
            pauth = request.headers.get(b"Proxy-Authorization", None)
            httpauth = b"Basic " + base64.b64encode(b":".join(self.auth))
            if httpauth != pauth:
                await self._write(
                    request.ver + b" 407 Proxy Authentication Required\r\n"
                    b"Connection: close\r\n"
                    b'Proxy-Authenticate: Basic realm="Shadowproxy Auth"\r\n\r\n'
                )
                raise ProtocolError("Unauthorized HTTP Request")
        if request.method == b"CONNECT":
            host, _, port = request.path.partition(b":")
            target_addr = (host.decode(), int(port))
        else:
            raise ProtocolError("only http connect is supported")
            url = urlparse(request.path)
            if not url.hostname:
                error_msg = "hostname is needed"
                await self._write(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Connection: close\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"Content-Length: 2\r\n\r\n"
                )
                await self._write(error_msg.encode())
                raise ProtocolError(error_msg)
            target_addr = (url.hostname.decode(), url.port or 80)
        remote_parser = await ctx.create_client(target_addr)
        if request.method == b"CONNECT":
            await self._write(b"HTTP/1.1 200 Connection: Established\r\n\r\n")
        await remote_parser.init_client(target_addr)
        return remote_parser

    async def init_client(self, target_addr):
        target_host, target_port = target_addr
        target_address = f"{target_host}:{target_port}"
        headers_str = (
            f"CONNECT {target_address} HTTP/1.1\r\n"
            f"Host: {target_address}\r\n"
            f"User-Agent: shadowproxy\r\n"
            "Proxy-Connection: Keep-Alive\r\n"
        )
        if self.auth:
            headers_str += "Proxy-Authorization: Basic {}\r\n".format(
                base64.b64encode(b":".join(self.auth)).decode()
            )
        headers_str += "\r\n"
        await self._write(headers_str.encode())
        response = await self.reader.pull(HTTPResponse)
        if response.code != b"200":
            raise ProtocolError(f"bad status code: {response.code} {response.status}")
        return response
