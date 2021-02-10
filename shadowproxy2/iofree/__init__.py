"""`iofree` is an easy-to-use and powerful library \
to help you implement network protocols and binary parsers."""
from struct import Struct
from typing import Any, Callable, Generator, Optional

from .parser import Parser, Traps

__version__ = "0.2.4"


def read(nbytes: int = 0) -> Generator[tuple, bytes, bytes]:
    """
    if nbytes = 0, read as many as possible, empty bytes is valid;
    if nbytes > 0, read *exactly* ``nbytes``
    """
    return (yield (Traps._read, nbytes))


def read_more(nbytes: int = 1) -> Generator[tuple, bytes, bytes]:
    """
    read *at least* ``nbytes``
    """
    if nbytes <= 0:
        raise ValueError(f"nbytes must > 0, but got {nbytes}")
    return (yield (Traps._read_more, nbytes))


def read_until(
    data: bytes, *, return_tail: bool = True
) -> Generator[tuple, bytes, bytes]:
    """
    read until some bytes appear
    """
    return (yield (Traps._read_until, data, return_tail))


def read_format(fmt: str) -> Generator[tuple, tuple, tuple]:
    """
    read specific formatted data
    """
    return (yield (Traps._read_struct, Struct(fmt)))


def read_struct(struct_obj: Struct) -> Generator[tuple, tuple, tuple]:
    """
    read raw struct formatted data
    """
    return (yield (Traps._read_struct, struct_obj))


def read_int(
    nbytes: int, byteorder: str = "big", *, signed: bool = False
) -> Generator[tuple, int, int]:
    """
    read some bytes as integer
    """
    if nbytes <= 0:
        raise ValueError(f"nbytes must > 0, but got {nbytes}")
    return (yield (Traps._read_int, nbytes, byteorder, signed))


def wait() -> Generator[tuple, bytes, Optional[object]]:
    """
    wait for next send event
    """
    return (yield (Traps._wait,))


def peek(nbytes: int = 1) -> Generator[tuple, bytes, bytes]:
    """
    peek many bytes without taking them away from buffer
    """
    if nbytes <= 0:
        raise ValueError(f"nbytes must > 0, but got {nbytes}")
    return (yield (Traps._peek, nbytes))


def wait_event() -> Generator[tuple, Any, Any]:
    """
    wait for an event
    """
    return (yield (Traps._wait_event,))


def get_parser() -> Generator[tuple, Parser, Parser]:
    "get current parser object"
    return (yield (Traps._get_parser,))


def parser(func: Callable = None, *, creator=lambda _: Parser(_)) -> Callable:
    def decorator(generator_func: Callable) -> Callable:
        "decorator function to wrap a generator"

        def create_parser(*args, **kwargs) -> Parser:
            nonlocal creator
            return creator(generator_func(*args, **kwargs))

        generator_func.parser = create_parser
        return generator_func

    return decorator if func is None else decorator(func)
