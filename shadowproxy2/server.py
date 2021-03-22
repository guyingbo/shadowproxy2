import asyncio
import signal
import contextlib


async def run_server(ctx_list):
    loop = asyncio.get_running_loop()
    quit_event = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, quit_event.set)

    async with contextlib.AsyncExitStack() as stack:
        for ctx in ctx_list:
            ctx.stack = stack
            print(
                f"server running at {ctx.inbound_ns.transport}:{ctx.inbound_ns.host}:{ctx.inbound_ns.port} -> {ctx.outbound_ns}"
            )
            await ctx.create_server()

        await quit_event.wait()
