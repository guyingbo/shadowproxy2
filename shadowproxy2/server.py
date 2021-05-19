import asyncio
import contextlib
import signal
from asyncio.tasks import Task


class TaskFactory:
    def __init__(self):
        self.tasks = set()

    def __call__(self, loop, coro):
        task = Task(coro, loop=loop)
        if task._source_traceback:
            del task._source_traceback[-1]
        self.tasks.add(task)
        task.add_done_callback(self.tasks.remove)
        return task

    def close(self):
        print("close")
        for task in self.tasks:
            if not task.done():
                task.cancel()


async def run_server(ctx_list):
    loop = asyncio.get_running_loop()
    quit_event = asyncio.Event()
    factory = TaskFactory()
    loop.set_task_factory(factory)
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
