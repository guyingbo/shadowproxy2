from dependency_injector import containers, providers

from .parsers.base import NullParser
from .throttle import Throttle
from .urlparser import BoundNamespace
from .ciphers import ChaCha20IETFPoly1305
from .parsers import socks5, socks4, aead, http, trojan
import asyncio


class Container(containers.DeclarativeContainer):
    inbound_ns = providers.Dependency(instance_of=BoundNamespace)
    outbound_ns = providers.Dependency()
    quic_client_lock = providers.Singleton(asyncio.Lock)
    inbound_parser = providers.Selector(
        providers.Factory(lambda ns: "c1" if ns is None else "c2", inbound_ns),
        c1=providers.Factory(NullParser),
        c2=providers.Selector(
            inbound_ns.provided.proxy,
            socks5=providers.Factory(
                socks5.Socks5Parser,
                inbound_ns.provided.username,
                inbound_ns.provided.password,
            ),
            socks4=providers.Factory(socks4.Socks4Parser),
            ss=providers.Selector(
                providers.Factory(
                    lambda ns: "plain" if ns.username is None else "aead", inbound_ns
                ),
                aead=providers.Factory(
                    aead.AEADParser,
                    providers.Singleton(
                        ChaCha20IETFPoly1305, inbound_ns.provided.password
                    ),
                ),
                plain=providers.Factory(aead.PlainParser),
            ),
            plain=providers.Factory(aead.PlainParser),
            http=providers.Factory(
                http.HTTPParser,
                inbound_ns.provided.username,
                inbound_ns.provided.password,
            ),
            trojan=providers.Factory(
                trojan.TrojanParser,
                inbound_ns.provided.username,
                inbound_ns.provided.password,
            ),
        ),
    )
    outbound_parser = providers.Selector(
        providers.Factory(lambda ns: "c1" if ns is None else "c2", outbound_ns),
        c1=providers.Factory(NullParser),
        c2=providers.Selector(
            outbound_ns.provided.proxy,
            socks5=providers.Factory(
                socks5.Socks5Parser,
                outbound_ns.provided.username,
                outbound_ns.provided.password,
            ),
            socks4=providers.Factory(socks4.Socks4Parser),
            ss=providers.Selector(
                providers.Factory(
                    lambda ns: "plain" if ns.username is None else "aead", outbound_ns
                ),
                aead=providers.Factory(
                    aead.AEADParser,
                    providers.Singleton(
                        ChaCha20IETFPoly1305, outbound_ns.provided.password
                    ),
                ),
                plain=providers.Factory(aead.PlainParser),
            ),
            plain=providers.Factory(aead.PlainParser),
            http=providers.Factory(
                http.HTTPParser,
                outbound_ns.provided.username,
                outbound_ns.provided.password,
            ),
            trojan=providers.Factory(
                trojan.TrojanParser,
                outbound_ns.provided.username,
                outbound_ns.provided.password,
            ),
        ),
    )
    upload_throttle = providers.Singleton(
        lambda ns: Throttle(ns.ul * 1024) if ns else None, inbound_ns
    )
    download_throttle = providers.Singleton(
        lambda ns: Throttle(ns.dl * 1024) if ns else None, inbound_ns
    )
