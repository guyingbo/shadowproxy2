import abc
import asyncio
import enum
from contextvars import ContextVar
from collections import deque
from struct import Struct, pack
from typing import Any, Callable, Dict, List, Mapping, Optional, Type, Union

_parent_stack: deque["BinarySchema"] = deque()
straightway = ContextVar("straightway", default=False)


class Unit(abc.ABC):
    """Unit is the base class of all units. \
    If you can build your own unit class, you must inherit from it"""

    @abc.abstractmethod
    async def get_value(self, buffer):
        "get object you want from bytes"

    @abc.abstractmethod
    def __call__(self, obj) -> bytes:
        "convert user-given object to bytes"


class BinarySchemaMetaclass(type):
    def __new__(mcls, name, bases, namespace, **kwargs):
        fields: Dict[str, FieldType] = {}
        for key, member in namespace.items():
            if isinstance(member, (Unit, BinarySchemaMetaclass)):
                fields[key] = member
                namespace[key] = MemberDescriptor(key, member)
        namespace["_fields"] = fields
        return super().__new__(mcls, name, bases, namespace)

    def __str__(cls):
        s = ", ".join(f"{name}={field}" for name, field in cls._fields.items())
        return f"{cls.__name__}({s})"

    async def get_value(cls, buffer):
        "get `BinarySchema` object from bytes"
        mapping: Dict[str, Any] = {}
        buffer._mapping_stack.append(mapping)
        try:
            for name, field in cls._fields.items():
                mapping[name] = await field.get_value(buffer)
        except Exception as e:
            e.args += (mapping,)
            raise
        finally:
            buffer._mapping_stack.pop()
        return cls(*mapping.values())


class BinarySchema(metaclass=BinarySchemaMetaclass):
    """The main class for users to define their own binary structures"""

    def __init__(self, *args):
        self._modified = True
        if len(args) != len(self.__class__._fields):
            raise ValueError(
                f"need {len(self.__class__._fields)} args, got {len(args)}"
            )
        self.values = {}
        self.bins = {}
        _parent_stack.append(self)
        try:
            for arg, (name, field) in zip(args, self.__class__._fields.items()):
                setattr(self, name, arg)
        finally:
            _parent_stack.pop()

        if hasattr(self, "__post_init__"):
            self.__post_init__()

    def member_get(self, name):
        return self.values[name]

    def member_set(self, name, value, binary):
        self.bins[name] = binary
        self.values[name] = value
        self._modified = True

    @property
    def binary(self) -> bytes:
        if self._modified:
            self._binary = b"".join(self.bins.values())
            self._modified = False
        return self._binary

    def __str__(self):
        sl = []
        for name in self.__class__._fields:
            value = getattr(self, name)
            sl.append(f"{name}={value!r}")
        s = ", ".join(sl)
        return f"{self.__class__.__name__}({s})"

    def __repr__(self):
        return f"<{self}>"

    def __eq__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            return False
        for name in self.__class__._fields:
            if getattr(self, name) != getattr(other, name):
                return False
        return True


FieldType = Union[Type[BinarySchema], Unit]


class MemberDescriptor:
    __slots__ = ("key", "member")

    def __init__(self, key: str, member: FieldType):
        self.key = key
        self.member = member

    def __get__(self, obj: Optional[BinarySchema], owner):
        if obj is None:
            return self.member
        return obj.member_get(self.key)

    def __set__(self, obj: BinarySchema, value):
        if isinstance(self.member, BinarySchemaMetaclass):
            binary = value.binary
        elif isinstance(self.member, Unit):
            binary = self.member(value)
        if value is ...:
            assert isinstance(self.member, MustEqual)
            value = self.member.value
        obj.member_set(self.key, value, binary)


class AioBuffer:
    def __init__(self, data: Optional[bytearray] = None):
        self._buf = data or bytearray()
        self._next = None
        self._args = ()
        self._waiter = None
        self._mapping_stack: deque = deque()

    def __len__(self):
        return len(self._buf)

    def __repr__(self):
        return f"AioBuffer<{self._buf}>"

    def push(self, data):
        self._buf.extend(data)
        if self._next is not None:
            self._next(*self._args)

    def push_eof(self):
        if self._waiter is not None:
            self._waiter.set_exception(EOFError())

    def close(self):
        if self._waiter is not None:
            self._waiter.set_exception(ConnectionError("closed"))

    def read_all(self):
        r = bytes(self._buf)
        del self._buf[:]
        return r

    def _peek(self, nbytes):
        if len(self._buf) < nbytes:
            return
        result = self._buf[:nbytes]
        self._next = None
        if self._waiter is None:
            return result
        self._waiter.set_result(result)

    def _read_all(self):
        if not self._buf:
            return
        r = self._buf[:]
        del self._buf[:]
        return r

    def _read_exactly(self, nbytes: int) -> Optional[bytearray]:
        if len(self._buf) < nbytes:
            return
        result = self._buf[:nbytes]
        del self._buf[:nbytes]
        self._next = None
        if self._waiter is None:
            return result
        self._waiter.set_result(result)

    def _read_struct(self, struct: Struct):
        size = struct.size
        if len(self._buf) < size:
            return
        result = struct.unpack_from(self._buf)
        del self._buf[:size]
        self._next = None
        if self._waiter is None:
            return result
        self._waiter.set_result(result)

    def _read_until(self, data, return_tail: bool) -> Optional[bytearray]:
        index = self._buf.find(data)
        if index == -1:
            return
        end = index + len(data)
        result = self._buf[: end if return_tail else index]
        del self._buf[:end]
        self._next = None
        if self._waiter is None:
            return result
        self._waiter.set_result(result)

    async def pull(self, obj: Union[int, Struct, str, Unit, Type[BinarySchema]]):
        if isinstance(obj, int):
            if obj > 0:
                self._next = self._read_exactly
                self._args = (obj,)
            else:
                self._next = self._read_all
                self._args = ()
        elif isinstance(obj, Struct):
            self._next = self._read_struct
            self._args = (obj,)
        elif isinstance(obj, str):
            self._next = self._read_struct
            self._args = (Struct(obj),)
        elif isinstance(obj, (Unit, BinarySchemaMetaclass)):
            return await obj.get_value(self)
        else:
            raise TypeError(f"unknown object type: {type(obj)}")
        res = self._next(*self._args)
        if res is None:
            if straightway.get():
                raise ValueError("pull failed")
            self._waiter = asyncio.Future()
            try:
                res = await self._waiter
            finally:
                self._waiter = None
        return res

    async def pull_until(self, data, *, return_tail: bool = True):
        self._next = self._read_until
        self._args = (data, return_tail)
        res = self._next(*self._args)
        if res is None:
            self._waiter = asyncio.Future()
            try:
                res = await self._waiter
            finally:
                self._waiter = None
        return res

    async def peek(self, nbytes: int):
        self._next = self._peek
        self._args = (nbytes,)
        res = self._next(*self.args)
        if res is None:
            self._waiter = asyncio.Future()
            try:
                res = await self._waiter
            finally:
                self._waiter = None
        return res


class SingleStructUnit(Unit):
    def __init__(self, format_: str):
        self._struct = Struct(format_)

    def __str__(self):
        return f"{self.__class__.__name__}({self._struct.format})"

    async def get_value(self, buffer):
        return (await buffer.pull(self._struct))[0]

    def __call__(self, obj) -> bytes:
        return self._struct.pack(obj)


class IntUnit(Unit):
    def __init__(self, length: int, byteorder: str, signed: bool = False):
        self.length = length
        self.byteorder = byteorder
        self.signed = signed

    async def get_value(self, buffer):
        return await buffer.read_int(
            self.length, byteorder=self.byteorder, signed=self.signed
        )

    def __call__(self, obj: int) -> bytes:
        return obj.to_bytes(self.length, self.byteorder, signed=self.signed)


i8 = SingleStructUnit("b")
u8 = SingleStructUnit("B")
i16 = SingleStructUnit("h")
i16be = SingleStructUnit(">h")
u16 = SingleStructUnit("H")
u16be = SingleStructUnit(">H")
i32 = SingleStructUnit("i")
i32be = SingleStructUnit(">i")
u32 = SingleStructUnit("I")
u32be = SingleStructUnit(">I")
i64 = SingleStructUnit("q")
i64be = SingleStructUnit(">q")
u64 = SingleStructUnit("Q")
ut64be = SingleStructUnit(">Q")
f16 = SingleStructUnit("e")
f16be = SingleStructUnit(">e")
f32 = SingleStructUnit("f")
f32be = SingleStructUnit(">f")
f64 = SingleStructUnit("d")
f64be = SingleStructUnit(">d")
i24 = IntUnit(3, "little", signed=True)
i24be = IntUnit(3, "big", signed=True)
u24 = IntUnit(3, "little", signed=False)
u24be = IntUnit(3, "big", signed=False)


class Bytes(Unit):
    def __init__(self, length: int):
        self.length = length

    def __str__(self):
        return f"{self.__class__.__name__}({self.length})"

    async def get_value(self, buffer):
        if self.length >= 0:
            return await buffer.pull(self.length)
        else:
            return buffer.read()

    def __call__(self, obj) -> bytes:
        return bytes(obj)


class MustEqual(Unit):
    def __init__(self, unit: Unit, value):
        self.unit = unit
        self.value = value

    def __str__(self):
        return f"{self.__class__.__name__}({self.unit}, {self.value})"

    async def get_value(self, buffer):
        result = await self.unit.get_value(buffer)
        if self.value != result:
            raise ValueError(f"expect {self.value}, got {result}")
        return result

    def __call__(self, obj) -> bytes:
        if obj is not ...:
            if self.value != obj:
                raise ValueError(f"expect {self.value}, got {obj}")
        return self.unit(self.value)


class EndWith(Unit):
    def __init__(self, bytes_: bytes):
        self.bytes_ = bytes_

    def __str__(self):
        return f"{self.__class__.__name__}({self.bytes_})"

    async def get_value(self, buffer):
        return await buffer.pull_until(self.bytes_, return_tail=False)

    def __call__(self, obj: bytes) -> bytes:
        return obj + self.bytes_


class LengthPrefixedBytes(Unit):
    def __init__(self, length_unit: Union[SingleStructUnit, IntUnit]):
        self.length_unit = length_unit

    def __str__(self):
        return f"{self.__class__.__name__}({self.length_unit})"

    async def get_value(self, buffer):
        length = await self.length_unit.get_value(buffer)
        return (await buffer.pull(f"{length}s"))[0]

    def __call__(self, obj: bytes) -> bytes:
        length = len(obj)
        return self.length_unit(length) + pack(f"{length}s", obj)


class Switch(Unit):
    def __init__(self, ref: str, cases: Mapping[Any, FieldType]):
        self.ref = ref
        self.cases = cases

    def __str__(self):
        return f"{self.__class__.__name__}({self.ref}, {self.cases})"

    async def get_value(self, buffer):
        mapping = buffer._mapping_stack[-1]
        unit = self.cases[mapping[self.ref]]
        return await unit.get_value(buffer)

    def __call__(self, obj) -> bytes:
        parent = _parent_stack[-1]
        real_field = self.cases[getattr(parent, self.ref)]
        return real_field(obj) if isinstance(real_field, Unit) else obj.binary


class SizedIntEnum(Unit):
    def __init__(
        self,
        size_unit: Union[SingleStructUnit, IntUnit],
        enum_class: Type[enum.IntEnum],
    ):
        self.size_unit = size_unit
        self.enum_class = enum_class

    def __str__(self):
        return f"{self.__class__.__name__}({self.size_unit}, {self.enum_class})"

    async def get_value(self, buffer):
        v = await self.size_unit.get_value(buffer)
        return self.enum_class(v)

    def __call__(self, obj: enum.IntEnum) -> bytes:
        return self.size_unit(obj.value)


class Convert(Unit):
    def __init__(self, unit: Unit, *, encode: Callable, decode: Callable):
        self.unit = unit
        self.encode = encode
        self.decode = decode

    def __str__(self):
        return (
            f"{self.__class__.__name__}"
            f"({self.unit}, encode={self.encode}, decode={self.decode})"
        )

    async def get_value(self, buffer):
        v = await self.unit.get_value(buffer)
        return self.decode(v)

    def __call__(self, obj: Any) -> bytes:
        return self.unit(self.encode(obj))


class String(Convert):
    def __init__(self, length: int, encoding="utf-8"):
        super().__init__(
            Bytes(length),
            encode=lambda x: x.encode(encoding),
            decode=lambda x: x.decode(encoding),
        )


class LengthPrefixedString(Convert):
    def __init__(self, length_unit: Union[SingleStructUnit, IntUnit], encoding="utf-8"):
        super().__init__(
            LengthPrefixedBytes(length_unit),
            encode=lambda x: x.encode(encoding),
            decode=lambda x: x.decode(encoding),
        )


def Group(**fields: Dict[str, FieldType]) -> Type[BinarySchema]:
    return type("Group", (BinarySchema,), fields)


class LengthPrefixedObject(Unit):
    def __init__(
        self, length_unit: Union[SingleStructUnit, IntUnit], object_unit: FieldType
    ):
        self.length_unit = length_unit
        self.object_unit = object_unit

    def __str__(self):
        return f"{self.__class__.__name__}({self.length_unit}, {self.object_unit})"

    async def get_value(self, buffer):
        length = await self.length_unit.get_value(buffer)
        data = await buffer.pull(length)
        temp_buffer = AioBuffer(data)
        token = straightway.set(True)
        try:
            obj = await self.object_unit.get_value(temp_buffer)
        finally:
            straightway.reset(token)
        if len(temp_buffer) > 0:
            raise ValueError("extra bytes left")
        return obj

    def __call__(self, obj: FieldType) -> bytes:
        bytes_ = (
            obj.binary
            if isinstance(self.object_unit, BinarySchemaMetaclass)
            else self.object_unit(obj)
        )
        return self.length_unit(len(bytes_)) + bytes_


class LengthPrefixedObjectList(LengthPrefixedObject):
    async def get_value(self, buffer):
        length = await self.length_unit.get_value(buffer)
        data = await buffer.pull(length)
        temp_buffer = AioBuffer(data)
        lst = []
        token = straightway.set(True)
        try:
            while len(temp_buffer) > 0:
                lst.append(await self.object_unit.get_value(temp_buffer))
        finally:
            straightway.reset(token)
        return lst

    def __call__(self, obj_list: List[FieldType]) -> bytes:
        if isinstance(self.object_unit, BinarySchemaMetaclass):
            bytes_ = b"".join(bs.binary for bs in obj_list)
        elif isinstance(self.object_unit, Unit):
            bytes_ = b"".join(self.object_unit(bs) for bs in obj_list)
        return self.length_unit(len(bytes_)) + bytes_
