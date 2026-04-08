from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


class PasswordHasher:
    _ALGORITHM = "scrypt"
    _N = 2**14
    _R = 8
    _P = 1
    _DKLEN = 64
    _SALT_BYTES = 16

    def hash_password(self, password: str) -> str:
        normalized = str(password or "")
        if not normalized:
            raise ValueError("Password must not be empty")

        salt = secrets.token_bytes(self._SALT_BYTES)
        digest = hashlib.scrypt(
            normalized.encode("utf-8"),
            salt=salt,
            n=self._N,
            r=self._R,
            p=self._P,
            dklen=self._DKLEN,
        )
        return "$".join(
            [
                self._ALGORITHM,
                str(self._N),
                str(self._R),
                str(self._P),
                base64.b64encode(salt).decode("ascii"),
                base64.b64encode(digest).decode("ascii"),
            ]
        )

    def verify_password(self, password: str, password_hash: str | None) -> bool:
        if not password_hash:
            return False

        try:
            algorithm, n, r, p, salt_b64, digest_b64 = password_hash.split("$", 5)
        except ValueError:
            return False

        if algorithm != self._ALGORITHM:
            return False

        try:
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected_digest = base64.b64decode(digest_b64.encode("ascii"))
        except Exception:
            return False

        actual_digest = hashlib.scrypt(
            str(password or "").encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected_digest),
        )
        return hmac.compare_digest(actual_digest, expected_digest)
