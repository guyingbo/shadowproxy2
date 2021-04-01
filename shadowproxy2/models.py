from enum import Enum, unique

from pydantic import BaseModel


@unique
class TransportEnum(Enum):
    tcp = "tcp"
    kcp = "kcp"
    quic = "quic"
    udp = "udp"
    tls = "tls"


@unique
class ProxyEnum(Enum):
    socks5 = "socks5"
    socks4 = "socks4"
    ss = "ss"
    http = "http"
    tunnel = "tunnel"
    red = "red"


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
    host: str
    port: int
    via: str = None
    name: str = None
    ul: int = None  # max upload traffic speed per connection(KB/s)
    dl: int = None  # max download traffic speed per connection(KB/s)

    class Config:
        use_enum_values = True
        extra = "forbid"

    def __str__(self):
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.transport}+{self.proxy}://{auth}{self.host}:{self.port}"
