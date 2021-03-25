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


class BoundNamespace(BaseModel):
    transport: TransportEnum
    proxy: ProxyEnum
    username: str = None
    password: str = None
    host: str
    port: int
    via: str = None
    name: str = None

    class Config:
        use_enum_values = True
        extra = "forbid"
