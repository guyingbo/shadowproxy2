# Token Bucket Algorithm:
# https://dev.to/satrobit/rate-limiting-using-the-token-bucket-algorithm-3cjh
import asyncio
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Controllable(Protocol):
    def pause(self) -> None:
        ...

    def resume(self) -> None:
        ...


class Throttle:
    def __init__(self, rate: int, time_window: float = 0.5):
        """
        Token Bucket Algorithm
        @param rate: number of tokens added to the bucket per second
        @param time_window: the tokens are added in this time frame
        """
        self.rate = rate
        self.time_window = time_window
        self.tokens = rate * time_window
        self.bucket = self.tokens
        self.last_check = time.monotonic()

    def update_rate(self, rate):
        self.rate = rate
        self.tokens = rate * self.time_window

    def consume(self, packets: int, controllable: Controllable):
        current = time.monotonic()
        time_passed = current - self.last_check
        self.last_check = current

        self.bucket += int(time_passed * self.rate)

        if self.bucket > self.tokens:
            self.bucket = self.tokens

        self.bucket -= packets
        if self.bucket < 1:
            loop = asyncio.get_running_loop()
            controllable.pause()
            loop.call_later((1 - self.bucket) / self.rate, controllable.resume)


class ProtocolProxy:
    throttles = {}

    def __init__(self, protocol, throttle):
        self.protocol = protocol
        protocol.proxy_ref = self
        self.throttle = throttle

        # self.received = 0
        # self.last_check = time.monotonic()

    def __getattr__(self, name):
        return getattr(self.protocol, name)

    def __str__(self):
        return str(self.protocol)

    def __repr__(self):
        return repr(self.protocol)

    def data_received(self, data):
        self.throttle.consume(len(data), self)
        self.protocol.data_received(data)

        # self.received += len(data)

    def pause(self):
        # current = time.monotonic()
        # time_passed = current - self.last_check
        # self.last_check = current
        # print(f"{time_passed:.1f}", int(self.received // time_passed // 1024))
        # self.received = 0

        if hasattr(self.protocol, "transport"):
            self.protocol.transport.pause_reading()

    def resume(self):
        if hasattr(self.protocol, "transport"):
            self.protocol.transport.resume_reading()
