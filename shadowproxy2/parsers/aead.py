import types

import click

from ..aiobuffer.socks5 import Addr
from .base import NullParser


class AEADParser(NullParser):
    def __init__(self, cipher):
        self.cipher = cipher
        self._cipher_buf = bytearray()
        self._reader = self._create_reader()

    def set_rw(self, reader, writer):
        super().set_rw(reader, writer)

        def _feed_data(this, data):
            self._cipher_buf.extend(data)
            while True:
                try:
                    plaintext = self._reader.send(None)
                except Exception as e:
                    click.secho(f"=={e}", fg="red")
                    this.set_exception(e)
                    return
                if plaintext is None:
                    return
                this.origin_feed_data(plaintext)

        self.reader.origin_feed_data = self.reader.feed_data
        self.reader.feed_data = types.MethodType(_feed_data, self.reader)
        if self.reader._buffer:
            self.reader._buffer, _buffer = bytearray(), self.reader._buffer
            self.reader.feed_data(_buffer)

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

    async def server(self, ctx):
        addr = await self.reader.pull(Addr)
        target_addr = (addr.host, addr.port)
        remote_parser = await ctx.create_client(target_addr)
        packet, self.encrypt = self.cipher.make_encrypter()
        await self._write(packet)
        await remote_parser.init_client(target_addr)
        return remote_parser

    async def write(self, data):
        packet = self.encrypt(data)
        await self._write(packet)

    async def init_client(self, target_addr):
        packet, self.encrypt = self.cipher.make_encrypter()
        await self._write(packet)
        addr = Addr.from_tuple(target_addr)
        await self.write(addr.binary)


class PlainParser(NullParser):
    async def server(self, ctx):
        addr = await self.reader.pull(Addr)
        target_addr = (addr.host, addr.port)
        remote_parser = await ctx.create_client(target_addr)
        await remote_parser.init_client(target_addr)
        return remote_parser

    async def init_client(self, target_addr):
        addr = Addr.from_tuple(target_addr)
        await self.write(addr.binary)
