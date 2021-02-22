import asyncio
import resource

import click

from .config import config
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


def validate_urls(ctx, urls):
    for url in urls:
        if url.proxy == "socks4" and (url.username or url.password):
            print("socks4 does not support authorization, ignore username and password")
            # raise click.BadParameter("haha")
    return urls


@click.command(help=f"INGRESS OR EGRESS format: {url_format}")
@click.argument("ingress", nargs=-1, required=True, type=URL, callback=validate_urls)
@click.option(
    "-r",
    "egress",
    metavar="EGRESS",
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
def main(ingress, egress, cert_chain, key_file, ca_cert, verbose):
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (50000, 50000))
    except Exception:
        pass
    config.cert_chain = cert_chain
    config.key_file = key_file
    config.ca_cert = ca_cert
    config.verbose = verbose
    egress_dict = {getattr(ns, "name", str(i + 1)): ns for i, ns in enumerate(egress)}
    ctx_list = [
        ProxyContext(
            ingress_ns,
            egress_dict.get(ingress_ns.via) if hasattr(ingress_ns, "via") else None,
        )
        for ingress_ns in ingress
    ]
    asyncio.run(run_server(ctx_list))


if __name__ == "__main__":
    main()
