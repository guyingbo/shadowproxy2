import os
from hashlib import md5, sha1
from typing import Callable, Optional

import hkdf
from nacl import bindings


def EVP_BytesToKey(password: bytes, size: int, salt: bytes = b"") -> bytes:
    keybuf = []
    while len(b"".join(keybuf)) < size:
        keybuf.append(md5((keybuf[-1] if keybuf else b"") + password + salt).digest())
    return b"".join(keybuf)[:size]


class ChaCha20IETFPoly1305:
    """
    >>> cipher = ChaCha20IETFPoly1305('password')
    >>> salt, encrypt = cipher.make_encrypter()
    >>> decrypt = cipher.make_decrypter(salt)
    >>> for length in (30, 60, 20000):
    ...     rand_bytes = os.urandom(length)
    ...     ciphertext = encrypt(rand_bytes)
    ...     length_bytes = decrypt(ciphertext[:2+cipher.TAG_SIZE])
    ...     l = int.from_bytes(length_bytes, 'big')
    ...     if l < cipher.PACKET_LIMIT:
    ...         assert l == length
    ...         back_bytes = decrypt(ciphertext[2+cipher.TAG_SIZE:])
    ...         assert rand_bytes == back_bytes
    ...     else:
    ...         assert l == cipher.PACKET_LIMIT
    """

    KEY_SIZE = 32
    SALT_SIZE = 32
    NONCE_SIZE = 12
    TAG_SIZE = 16
    PACKET_LIMIT = 0x3FFF
    info = b"ss-subkey"

    def __init__(self, password: str):
        self.master_key = EVP_BytesToKey(
            password.encode("ascii", "ignore"), size=self.KEY_SIZE
        )

    def _random_salt(self) -> bytes:
        return os.urandom(self.SALT_SIZE)

    def _derive_subkey(self, salt: bytes) -> bytes:
        return hkdf.Hkdf(salt, self.master_key, sha1).expand(self.info, self.KEY_SIZE)

    def make_encrypter(self, salt: Optional[bytes] = None) -> (bytes, Callable):
        counter = 0
        salt = salt if salt is not None else self._random_salt()
        subkey = self._derive_subkey(salt)

        def _encrypt(plaintext: bytes) -> bytes:
            nonlocal counter
            nonce = counter.to_bytes(self.NONCE_SIZE, "little")
            counter += 1
            return bindings.crypto_aead_chacha20poly1305_ietf_encrypt(
                plaintext, b"", nonce, subkey
            )

        def encrypt(plaintext: bytes) -> bytes:
            if len(plaintext) <= self.PACKET_LIMIT:
                len_bytes = len(plaintext).to_bytes(2, "big")
                return _encrypt(len_bytes) + _encrypt(plaintext)
            else:
                return encrypt(plaintext[: self.PACKET_LIMIT]) + encrypt(
                    plaintext[self.PACKET_LIMIT :]
                )

        return salt, encrypt

    def make_decrypter(self, salt: bytes):
        counter = 0
        subkey = self._derive_subkey(salt)

        def decrypt(ciphertext: bytes) -> bytes:
            nonlocal counter
            nonce = counter.to_bytes(self.NONCE_SIZE, "little")
            counter += 1
            return bindings.crypto_aead_chacha20poly1305_ietf_decrypt(
                ciphertext, b"", nonce, subkey
            )

        return decrypt
