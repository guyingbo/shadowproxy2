"""`iofree` is an easy-to-use and powerful library \
to help you implement network protocols and binary parsers."""
from __future__ import annotations

import asyncio
import sys
import typing
from typing import Generator
from collections import deque
from enum import IntEnum, auto
from struct import Struct

from .buffer import Buffer, StarvingException
from .exceptions import NoResult, ParseError

_wait = object()
_no_result = object()


class Traps(IntEnum):
    _read = auto()
    _read_more = auto()
    _read_until = auto()
    _read_struct = auto()
    _read_int = auto()
    _wait = auto()
    _peek = auto()
    _wait_event = auto()
    _get_parser = auto()


class State(IntEnum):
    _state_wait = auto()
    _state_next = auto()
    _state_end = auto()


class Parser:
    def __init__(self, gen: Generator, buffer: Buffer = None):
        self.gen = gen
        self.buffer = buffer or Buffer()
        self.responses: deque = deque()
        self._input_events: deque = deque()
        self._output = bytearray()
        self._res = _no_result
        self._mapping_stack: deque = deque()
        self._next_value = None
        self._last_trap: tuple = None
        self._pos = -1
        self._state: State = State._state_next
        self._init()
        self._process()

    def _init(self):
        pass

    @classmethod
    def new(cls, gen: Generator, size: int = 4095) -> "Parser":
        return cls(gen, Buffer(size))

    def __repr__(self):
        return f"<{self.__class__.__qualname__}({self.gen})>"

    def parse(self, data: bytes, *, strict: bool = True) -> typing.Any:
        """
        parse bytes
        """
        self.data_received(data)
        if strict and self.has_more_data():
            raise ParseError(f"redundant data left: {self.readall()}")
        return self.get_result()

    def data_received(self, data: typing.ByteString | memoryview = b"") -> None:
        if data:
            self.buffer.push(data)
        self._process()

    def eof_received(self) -> None:
        if not self.finished():
            self.gen.throw(ParseError("eof received"))

    def respond(self, result) -> None:
        self.responses.append(result)

    @property
    def has_result(self) -> bool:
        return self._res is not _no_result

    def get_result(self) -> typing.Any:
        """
        raises *NoResult* exception if no result has been set
        """
        self._process()
        if not self.has_result:
            raise NoResult("no result")
        return self._res

    def set_result(self, result) -> None:
        self._res = result

    def finished(self) -> bool:
        return self._state is State._state_end

    def _process(self) -> None:
        if self._state is State._state_end:
            return
        self._state = State._state_next
        while self._state is State._state_next:
            self._next_state()

    def _next_state(self) -> None:
        if self._last_trap is None:
            try:
                trap, *args = self.gen.send(self._next_value)
            except StopIteration as e:
                self._state = State._state_end
                self.set_result(e.value)
                return
            except Exception:
                self._state = State._state_end
                tb = sys.exc_info()[2]
                raise ParseError(f"{self._next_value!r}").with_traceback(tb)
            else:
                if not isinstance(trap, Traps):
                    self._state = State._state_end
                    raise RuntimeError(f"Expect Traps object, but got: {trap}")
        else:
            trap, *args = self._last_trap
        result = getattr(self, trap.name)(*args)
        if result is _wait:
            self._state = State._state_wait
            self._last_trap = (trap, *args)
        else:
            self._state = State._state_next
            self._next_value = result
            self._last_trap = None

    def readall(self) -> bytes:
        """
        retrieve data from input back
        """
        return self._read(0)

    def has_more_data(self) -> bool:
        "indicate whether input has some bytes left"
        return self.buffer.data_size > 0

    def event_received(self, event: typing.Any) -> None:
        self._input_events.append(event)
        self._process()

    def _wait_event(self):
        if self._input_events:
            return self._input_events.popleft()
        return _wait

    def _wait(self) -> typing.Optional[object]:
        if not getattr(self, "_waiting", False):
            self._waiting = True
            return _wait
        self._waiting = False
        return None

    def _read(self, nbytes: int = 0) -> bytes:
        try:
            return self.buffer.pull(nbytes)
        except StarvingException:
            return _wait

    def _read_more(self, nbytes: int = 1) -> typing.Union[object, bytes]:
        try:
            return self.buffer.pull_amap(nbytes)
        except StarvingException:
            return _wait

    def _read_until(
        self, data: bytes, return_tail: bool = True
    ) -> typing.Union[object, bytes]:
        try:
            res = self.buffer.pull_until(
                data, init_pos=self._pos, return_tail=return_tail
            )
            self._pos = -1
            return res
        except StarvingException as e:
            self._pos = e.args[0]
            return _wait

    def _read_struct(self, struct_obj: Struct) -> typing.Union[object, tuple]:
        try:
            return self.buffer.pull_struct(struct_obj)
        except StarvingException:
            return _wait

    def _read_int(
        self, nbytes: int, byteorder: str = "big", signed: bool = False
    ) -> typing.Union[object, int]:
        try:
            return self.buffer.pull_int(nbytes, byteorder, signed)
        except StarvingException:
            return _wait

    def _peek(self, nbytes: int = 1) -> typing.Union[object, bytes]:
        try:
            return self.buffer.peek(nbytes)
        except StarvingException:
            return _wait

    def _get_parser(self) -> "Parser":
        return self

    def write(self, data: bytes) -> None:
        self._output.extend(data)

    def close(self):
        pass


class AsyncioParser(Parser):
    def _init(self):
        self.responses = asyncio.Queue()

    def respond(self, result):
        self.responses.put_nowait(result)

    def set_transport(self, transport):
        self.transport = transport

    def write(self, data: bytes) -> None:
        self.transport.write(data)

    def close(self):
        self.transport.close()
