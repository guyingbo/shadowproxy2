import click

from ..aiobuffer.buffer import AioBuffer
from ..aiobuffer.socks5 import Addr
from .base import NullParser


class AEADParser(NullParser):
    def __init__(self, cipher):
        self.buffer = AioBuffer()
        self.cipher = cipher
        self._cipher_buf = bytearray()
        self._reader = self._create_reader()

    def _pull_ciphertext(self, nbytes):
        while len(self._cipher_buf) < nbytes:
            yield
        data = bytes(self._cipher_buf[:nbytes])
        del self._cipher_buf[:nbytes]
        return data

    def _create_reader(self):
        salt = yield from self._pull_ciphertext(self.cipher.SALT_SIZE)
        decrypt = self.cipher.make_decrypter(salt)
        while True:
            chunk0 = yield from self._pull_ciphertext(2 + self.cipher.TAG_SIZE)
            length_bytes = decrypt(chunk0)
            length = int.from_bytes(length_bytes, "big")
            if length != length & 0x3FFF:  # 16 * 1024 - 1
                raise Exception("exceed the length limit")
            chunk1 = yield from self._pull_ciphertext(length + self.cipher.TAG_SIZE)
            yield decrypt(chunk1)

    def push(self, data):
        self._cipher_buf.extend(data)
        while True:
            try:
                plaintext = self._reader.send(None)
            except Exception as e:
                click.secho(f"=={e}", fg="red")
                self.transport.close()
                return
            if plaintext is None:
                return
            self.buffer.push(plaintext)

    async def server(self, inbound_stream):
        addr = await self.buffer.pull(Addr)
        target_addr = (addr.host, addr.port)
        outbound_stream = await inbound_stream.ctx.create_client(
            target_addr, inbound_stream.source_addr
        )
        packet, self.encrypt = self.cipher.make_encrypter()
        self.transport.write(packet)
        return outbound_stream

    def write(self, data):
        packet = self.encrypt(data)
        self.transport.write(packet)

    async def init_client(self, target_addr):
        packet, self.encrypt = self.cipher.make_encrypter()
        self.transport.write(packet)
        addr = Addr.from_tuple(target_addr)
        self.write(addr.binary)
