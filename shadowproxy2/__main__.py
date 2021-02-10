import asyncio
import click

from .server import run_server
from .urlparser import URLVisitor, grammar
from .context import ProxyContext

url_format = "[transport+]proxy://[username:password@][host]:port[?key=value]"


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


def validate(ctx, url: str):
    if url is None:
        return None
    try:
        tree = grammar.parse(url)
    except Exception:
        raise click.BadParameter(
            f"invalid proxy url format, here is the rules\n\n{grammar}"
        )
    visitor = URLVisitor()
    return visitor.visit(tree)


@click.command(help=f"INGRESS OR EGRESS format: {url_format}")
@click.argument("ingress", nargs=-1, required=True, type=URL)
@click.option(
    "-r",
    "egress",
    metavar="EGRESS",
    multiple=True,
    type=URL,
    help="default to direct connect",
)
def main(ingress, egress):
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
