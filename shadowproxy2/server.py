import asyncio
import contextlib
import signal


async def run_server(ctx_list):
    loop = asyncio.get_running_loop()
    quit_event = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, quit_event.set)
    # loop.add_signal_handler(signal.SIGINT, factory.close)

    async with contextlib.AsyncExitStack() as stack:
        for ctx in ctx_list:
            ctx.stack = stack
            print(
                f"server running at {ctx.inbound_ns} -> {ctx.outbound_ns}", flush=True
            )
            await ctx.create_server()

        await quit_event.wait()
