from struct import Struct


int8 = Struct("b")
uint8 = Struct("B")
int16 = Struct("h")
int16be = Struct(">h")
uint16 = Struct("H")
uint16be = Struct(">H")
int32 = Struct("i")
int32be = Struct(">i")
uint32 = Struct("I")
uint32be = Struct(">I")
int64 = Struct("q")
int64be = Struct(">q")
uint64 = Struct("Q")
uint64be = Struct(">Q")
float16 = Struct("e")
float16be = Struct(">e")
float32 = Struct("f")
float32be = Struct(">f")
float64 = Struct("d")
float64be = Struct(">d")


class StarvingException(Exception):
    pass


def _chr_len(x: int):
    return len(repr(chr(x))) - 2


# Buffer Structure
# @: data, -: blank
# [------------------------------------------] initial state
#  ^head&tail
#  ^data
# [@@@@@@@@----------------------------------] after first push
#  ^tail   ^head
# [-----@@@@@@@@@----------------------------] after first pull
#       ^tail    ^head
# [---------------------------------@@@@@@@@@] after pushing over size
#                                   ^tail    ^head
# [------------------------------------------] empty
#                   ^head&tail
# [@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@] full
#  ^tail                                     ^head
class Buffer:
    def __init__(self, size: int = 4095):
        if size < 1:
            raise ValueError("size must > 0")
        self.buf = bytearray(size)
        self.head = 0
        self.tail = 0
        self.size = size

    def __len__(self):
        return self._data_size()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"({bytes(self.buf)!r}, tail={self.tail}, head={self.head})"
        )

    def _available_size(self):
        return self.size - self.head + self.tail

    available_size = property(_available_size)

    def _data_size(self):
        return self.head - self.tail

    data_size = property(_data_size)

    def _right_blank_size(self):
        return self.size - self.head

    def clear(self) -> None:
        self.head = self.tail = 0

    def resize(self, size: int) -> None:
        if size < 1:
            raise ValueError("size must > 0")
        if self.size == size:
            return
        if self.size < size:
            self.buf.extend(b"\x00" * (size - self.size))
        else:  # self.size > size
            del self.buf[self.size - size :]
        self.size = size
        self.clear()

    def pprint(self) -> None:
        print("\n", repr(self.buf), sep="")
        if self.head > self.tail:
            len0 = len(repr(self.buf[: self.tail])) - 2
            len1 = _chr_len(self.buf[self.tail])
            len2 = len(repr(self.buf[self.tail + 1 : self.head])) - 14
            if self.head == self.size:
                len3 = 1
            else:
                len3 = _chr_len(self.buf[self.head])
            print(f"{' '*len0}{'t'*len1}{' '*len2}{'h'*len3}")
        else:  # self.head == self.tail:
            len0 = len(repr(self.buf[: self.tail])) - 2
            len1 = _chr_len(self.buf[self.tail])
            print(f"{' '*len0}{'^'*len1}")

    def is_full(self) -> bool:
        return self._available_size() == 0

    def is_empty(self) -> bool:
        return self.head == 0

    def next(self) -> memoryview:
        return memoryview(self.buf)[self.head :]

    def _adjust(self):
        length = self.head - self.tail
        if length == 0:
            self.head = self.tail = 0
        else:
            self.buf[:length] = self.buf[self.tail : self.head]
            self.tail = 0
            self.head = length

    def advance(self, nbytes: int) -> None:
        self.head = self.head + nbytes

    def scale_up(self, nbytes: int) -> None:
        self.buf.extend(b"\x00" * nbytes)
        self.size += nbytes

    def push_struct(self, struct_obj, *args) -> None:
        size: int = struct_obj.size
        a_size: int = self._available_size()
        if size > a_size:
            self.scale_up(size - a_size)
        if self._right_blank_size() < size:
            self._adjust()
        struct_obj.pack_into(self.buf, self.head, *args)
        self.advance(size)

    def push(self, bytes_like):
        length: int = len(bytes_like)
        a_size: int = self._available_size()
        if length > a_size:
            self.scale_up(length - a_size)
        if length > self._right_blank_size():
            self._adjust()
        self.buf[self.head : self.head + length] = bytes_like
        self.advance(length)

    def pull(self, nbytes: int = 0):
        if nbytes < 0:
            raise ValueError("nbytes must >= 0")
        if nbytes == 0:
            res = b"" + self.buf[self.tail : self.head]
            self.head = self.tail = 0
            return res
        if self._data_size() < nbytes:
            raise StarvingException
        start = self.tail
        self.tail += nbytes
        res = b"" + self.buf[start : self.tail]
        if self.head == self.tail:
            self.head = self.tail = 0
        return res

    def pull_amap(self, least_nbytes: int = 1):
        """
        pull as much as possible, at least nbytes
        """
        if least_nbytes < 1:
            raise ValueError("least_nbytes must >= 1")
        if self._data_size() < least_nbytes:
            raise StarvingException
        return self.pull(0)

    def peek(self, nbytes: int):
        if nbytes < 1:
            raise ValueError("nbytes must >= 1")
        if self._data_size() < nbytes:
            raise StarvingException
        return self.buf[self.tail : self.tail + nbytes]

    def pull_int(self, nbytes: int, byteorder: str, signed: bool):
        return int.from_bytes(self.pull(nbytes), byteorder, signed=signed)

    def pull_struct(self, struct_obj):
        size: int = struct_obj.size
        if self._data_size() < size:
            raise StarvingException
        return struct_obj.unpack(self.pull(size))

    def pull_until(self, bytes_like, *, init_pos: int = -1, return_tail: bool = True):
        length: int = len(bytes_like)
        if length == 0:
            raise ValueError("bytes_like must not be empty")
        if init_pos == -1:
            init_pos = self.tail
        index = self.buf.find(bytes_like, init_pos, self.head)
        if index == -1:
            init_pos = self.head - length + 1
            if init_pos < self.tail:
                init_pos = self.tail
            raise StarvingException(init_pos)
        start = self.tail
        self.tail = index + length
        if return_tail:
            return b"" + self.buf[start : self.tail]
        else:
            return b"" + self.buf[start:index]
