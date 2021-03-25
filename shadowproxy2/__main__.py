import asyncio
import resource

import click

from . import app
from .context import ProxyContext
from .server import run_server
from .urlparser import URLVisitor, grammar

url_format = "[transport+]proxy://[username:password@][host]:port[#key=value]"


class URLParamType(click.ParamType):
    name = "url"

    def convert(self, value, param, ctx):
        try:
            tree = grammar.parse(value)
            visitor = URLVisitor()
            return visitor.visit(tree)
        except Exception:
            self.fail(
                f"bad url format, here are the rules\n\n{grammar}",
                param,
                ctx,
            )


URL = URLParamType()


def validate_urls(ctx, param, urls):
    for url in urls:
        if url.proxy == "socks4" and (url.username or url.password):
            print("socks4 does not support authorization, ignore username and password")
            # raise click.BadParameter("haha")
        if url.proxy == "ss" and url.username not in ("chacha20-ietf-poly1305",):
            raise click.BadParameter("supported ss ciphers: chacha20-ietf-poly1305")
    return urls


@click.command(help=f"INBOUND OR OUTBOUND format: {url_format}")
@click.argument("inbound", nargs=-1, required=True, type=URL, callback=validate_urls)
@click.option(
    "-r",
    "outbound",
    metavar="OUTBOUND",
    multiple=True,
    type=URL,
    callback=validate_urls,
    help="default to direct connect",
)
@click.option(
    "--cert-chain",
    default="/Users/mac/Projects/aioquic/tests/ssl_cert.pem",
    type=click.Path(exists=True),
    help="certificate chain file path",
)
@click.option(
    "--key-file",
    default="/Users/mac/Projects/aioquic/tests/ssl_key.pem",
    type=click.Path(exists=True),
    help="private key file path",
)
@click.option(
    "--ca-cert",
    default="/Users/mac/Projects/aioquic/tests/pycacert.pem",
    type=click.Path(exists=True),
    help="CA certificate file path",
)
@click.option("-v", "--verbose", count=True)
def main(inbound, outbound, cert_chain, key_file, ca_cert, verbose):
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (50000, 50000))
    except Exception:
        pass
    app.settings = app.Settings(
        cert_chain=cert_chain, key_file=key_file, ca_cert=ca_cert, verbose=verbose
    )
    outbound_dict = {
        getattr(ns, "name", str(i + 1)): ns for i, ns in enumerate(outbound)
    }
    ctx_list = [
        ProxyContext(
            inbound_ns,
            outbound_dict.get(inbound_ns.via) if hasattr(inbound_ns, "via") else None,
        )
        for inbound_ns in inbound
    ]
    asyncio.run(run_server(ctx_list))


if __name__ == "__main__":
    main()
