import base64
from enum import Enum, unique

from pydantic import BaseModel


@unique
class TransportEnum(Enum):
    tcp = "tcp"
    kcp = "kcp"
    quic = "quic"
    udp = "udp"
    tls = "tls"
    ws = "ws"
    wss = "wss"


@unique
class ProxyEnum(Enum):
    socks5 = "socks5"
    socks4 = "socks4"
    ss = "ss"
    http = "http"
    tunnel = "tunnel"
    red = "red"
    trojan = "trojan"
    plain = "plain"


rate_mapping = {
    20: "144p",
    30: "240p",
    50: "360p",
    60: "480p",
    80: "720p",
    100: "1080p",
}


class BoundNamespace(BaseModel):
    transport: TransportEnum
    proxy: ProxyEnum
    username: str = None
    password: str = None
    path: str = None
    host: str
    port: int
    via: str = None
    name: str = None
    verify_ssl: bool = True
    ul: int = None  # max upload traffic speed per source ip(KB/s)
    dl: int = None  # max download traffic speed per source ip(KB/s)
    user: str = None
    pw: str = None

    class Config:
        use_enum_values = True
        extra = "forbid"

    def __str__(self):
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.transport}+{self.proxy}://{auth}{self.host}:{self.port}"

    @property
    def credentials(self):
        if self.user and self.pw:
            return (self.user, self.pw)

    @property
    def basic_auth_header(self):
        if self.user and self.pw:
            credentials = base64.b64encode(f"{self.user}:{self.pw}".encode()).decode()
            return [("Authorization", f"Basic {credentials}")]
