import asyncio
import signal
import contextlib


async def run_server(ctx_list):
    loop = asyncio.get_running_loop()
    quit_event = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, quit_event.set)

    async with contextlib.AsyncExitStack() as stack:
        for ctx in ctx_list:
            await stack.enter_async_context(ctx)
            print(
                f"server running at {ctx.ingress_ns.transport}:{ctx.ingress_ns.host}:{ctx.ingress_ns.port} -> {ctx.egress_ns}"
            )
            await ctx.create_server()

        await quit_event.wait()
