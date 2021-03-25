from pydantic import BaseModel, BaseSettings, FilePath
from enum import Enum, unique


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


class Settings(BaseSettings):
    cert_chain: FilePath = None
    key_file: FilePath = None
    ca_cert: FilePath = None
    verbose: int = 0


settings = None
