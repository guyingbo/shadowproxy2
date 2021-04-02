import base64
import re
from urllib.parse import urlparse

from .. import iofree
from ..iofree import schema
from ..iofree.exceptions import ProtocolError

HTTP_LINE = re.compile(b"([^ ]+) +(.+?) +(HTTP/[^ ]+)")
ABSOLUTE_PREFIX = re.compile(r"^(.*://)?[^/]*")


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


def server(username: str, password: str):
    auth = (username.encode(), password.encode())
    parser = yield from iofree.get_parser()
    request = yield from HTTPRequest.get_value()
    if auth:
        pauth = request.headers.get(b"Proxy-Authorization", None)
        httpauth = b"Basic " + base64.b64encode(b":".join(auth))
        if httpauth != pauth:
            parser.write(
                request.ver + b" 407 Proxy Authentication Required\r\n"
                b"Connection: close\r\n"
                b'Proxy-Authenticate: Basic realm="Shadowproxy Auth"\r\n\r\n'
            )
            parser.close()
            raise ProtocolError("Unauthorized HTTP Request")
    if request.method == b"CONNECT":
        host, _, port = request.path.partition(b":")
        target_addr = (host.decode(), int(port))
    else:
        raise ProtocolError("only http connect is supported")
        url = urlparse(request.path)
        if not url.hostname:
            error_msg = "hostname is needed"
            parser.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Connection: close\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: 2\r\n\r\n"
            )
            parser.write(error_msg.encode())
            raise ProtocolError(error_msg)
        target_addr = (url.hostname.decode(), url.port or 80)
    parser.respond(target_addr)
    yield from parser.wait_event()
    if request.method == b"CONNECT":
        parser.write(b"HTTP/1.1 200 Connection: Established\r\n\r\n")


def client(target_host: str, target_port: int, username: str, password: str):
    parser = yield from iofree.get_parser()
    target_address = f"{target_host}:{target_port}"
    if username is None or password is None:
        auth = None
    else:
        auth = username.encode(), password.encode()
    headers_str = (
        f"CONNECT {target_address} HTTP/1.1\r\n"
        f"Host: {target_address}\r\n"
        f"User-Agent: shadowproxy\r\n"
        "Proxy-Connection: Keep-Alive\r\n"
    )
    if auth:
        headers_str += "Proxy-Authorization: Basic {}\r\n".format(
            base64.b64encode(b":".join(auth)).decode()
        )
    headers_str += "\r\n"
    parser.write(headers_str.encode())

    response = yield from HTTPResponse.get_value()

    if response.code != b"200":
        raise ProtocolError(f"bad status code: {response.code} {response.status}")
