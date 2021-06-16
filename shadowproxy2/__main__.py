import asyncio
import resource
from os.path import abspath, dirname, join

import click
import uvloop

from . import app
from .context import ProxyContext
from .server import run_server
from .urlparser import URLVisitor, grammar

url_format = "[transport+]proxy://[username:password@][host]:port[#key1=value1,...]"
base_path = abspath(join(dirname(__file__), ".."))
ssl_cert_path = join(base_path, "certs", "ssl_cert.pem")
ssl_key_path = join(base_path, "certs", "ssl_key.pem")
pycacert_path = join(base_path, "certs", "pycacert.pem")
blacklist_path = join(base_path, "assets", "p2p_ip.txt")


class URLParamType(click.ParamType):
    name = "url"

    def convert(self, value, param, ctx):
        try:
            tree = grammar.parse(value)
            visitor = URLVisitor()
            return visitor.visit(tree)
        except Exception as e:
            self.fail(
                f"bad url format: {e}\nrules:\n{grammar}",
                param,
                ctx,
            )


URL = URLParamType()


def validate_urls(ctx, param, urls):
    for url in urls:
        if url.proxy == "socks4" and (url.username or url.password):
            click.secho(
                "socks4 does not support authorization, ignore username and password",
                fg="red",
            )
            # raise click.BadParameter("haha")
        if url.proxy == "ss" and url.username not in ("chacha20-ietf-poly1305", None):
            raise click.BadParameter("supported ss ciphers: chacha20-ietf-poly1305")
    return urls


@click.command(help=f"INBOUND OR OUTBOUND format: {url_format}")
@click.argument(
    "inbound_list",
    metavar="INBOUND",
    nargs=-1,
    required=True,
    type=URL,
    callback=validate_urls,
)
@click.option(
    "-r",
    "outbound_list",
    metavar="OUTBOUND",
    multiple=True,
    type=URL,
    callback=validate_urls,
    help="default to direct connect",
)
@click.option(
    "--cert-chain",
    default=ssl_cert_path,
    type=click.Path(exists=True),
    help=f"certificate chain file path, default to {ssl_cert_path}",
)
@click.option(
    "--key-file",
    default=ssl_key_path,
    type=click.Path(exists=True),
    help=f"private key file path, default to {ssl_key_path}",
)
@click.option(
    "--ca-cert",
    default=pycacert_path,
    type=click.Path(exists=True),
    help=f"CA certificate file path, default to {pycacert_path}",
)
@click.option(
    "-B",
    "--blacklist",
    default=blacklist_path,
    type=click.Path(exists=True),
    help="ip blacklist file",
)
@click.option(
    "--block-countries",
    type=str,
    help="Country code seperated by comma, only works for cloudfare+websocket mode",
)
@click.option("-v", "--verbose", count=True)
def main(
    inbound_list,
    outbound_list,
    cert_chain,
    key_file,
    ca_cert,
    verbose,
    block_countries,
    blacklist,
):
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (50000, 50000))
    except Exception:
        pass
    uvloop.install()
    app.settings = app.Settings(
        cert_chain=cert_chain,
        key_file=key_file,
        ca_cert=ca_cert,
        verbose=verbose,
        block_countries=set(block_countries.split(",")),
    )
    if blacklist:
        with open(blacklist, "r") as f:
            app.blacklist = set(line.strip() for line in f)
    outbound_dict = {ns.name or str(i + 1): ns for i, ns in enumerate(outbound_list)}
    ctx_list = [
        ProxyContext(
            inbound_ns,
            outbound_dict.get(inbound_ns.via) if inbound_ns.via else None,
        )
        for inbound_ns in inbound_list
    ]
    asyncio.run(run_server(ctx_list))


if __name__ == "__main__":
    main()
