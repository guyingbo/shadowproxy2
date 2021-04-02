from .. import iofree
from ..iofree.contrib.common import Addr


@iofree.parser
def reader(cipher):
    parser = yield from iofree.get_parser()
    parser.cipher = cipher
    salt = yield from iofree.read(cipher.SALT_SIZE)
    parser.decrypt = cipher.make_decrypter(salt)
    while True:
        payload = yield from _read_some()
        parser.respond(payload)


def _read_some():
    parser = yield from iofree.get_parser()
    chunk0 = yield from iofree.read(2 + parser.cipher.TAG_SIZE)
    length_bytes = parser.decrypt(chunk0)
    length = int.from_bytes(length_bytes, "big")
    if length != length & 0x3FFF:  # 16 * 1024 - 1
        raise Exception("exceed the length limit")
    chunk1 = yield from iofree.read(length + parser.cipher.TAG_SIZE)
    return parser.decrypt(chunk1)


def ss_server():
    parser = yield from iofree.get_parser()
    addr = yield from Addr
    parser.respond(addr)


def ss_client(target_addr):
    parser = yield from iofree.get_parser()
    yield from iofree.wait()
    addr = Addr.from_tuple(target_addr)
    parser.write(addr.binary)
    parser.respond(None)
