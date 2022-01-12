from .context import ProxyContext
from .urlparser import URLVisitor, grammar


class Client:
    """example:
    async def go():
        client = Client("ss://127.0.0.1:8527")
        parser = await client.connect("httpbin.org", 80)
        await parser.write(data_bytes)
        data = await parser.read_func(4096)
        print(data)

    asyncio.run(go())
    """

    def __init__(self, uri):
        self.uri = uri
        tree = grammar.parse(uri)
        visitor = URLVisitor()
        self.outbound_ns = visitor.visit(tree)

    async def connect(self, host: str, port: int):
        ctx = ProxyContext(None, self.outbound_ns)
        parser = await ctx.create_client((host, port))
        await parser.init_client((host, port))
        return parser

    async def make_httpbin_request(self):
        parser = await self.connect("httpbin.org", 80)
        await parser.write(
            b"\r\n".join(
                [
                    b"GET /ip HTTP/1.1",
                    b"Host: httpbin.org",
                    b"Accept: */*",
                    b"User-Agent: curl/7.64.1\r\n\r\n",
                ]
            )
        )
        await parser.read_func(4096)
        await parser.close()