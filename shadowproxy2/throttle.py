# Token Bucket Algorithm:
# https://dev.to/satrobit/rate-limiting-using-the-token-bucket-algorithm-3cjh
import asyncio
import time


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

    def consume(self, packets: int, event: asyncio.Event):
        current = time.monotonic()
        time_passed = current - self.last_check
        self.last_check = current

        self.bucket += int(time_passed * self.rate)

        if self.bucket > self.tokens:
            self.bucket = self.tokens

        self.bucket -= packets
        if self.bucket < 1:
            loop = asyncio.get_running_loop()
            event.clear()
            loop.call_later((1 - self.bucket) / self.rate, event.set)
