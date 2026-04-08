import asyncio
from urllib.parse import urlparse


class RedisClientError(Exception):
    pass


class AsyncRedisClient:
    def __init__(self, redis_url: str, timeout: float = 1.0):
        parsed = urlparse(redis_url)
        if parsed.scheme not in {"redis", "rediss"}:
            raise ValueError(f"Unsupported Redis URL scheme: {parsed.scheme}")

        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 6379
        self._password = parsed.password
        self._db = int(parsed.path.lstrip("/") or "0")
        self._ssl = parsed.scheme == "rediss"
        self._timeout = timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def ping(self) -> bool:
        response = await self._execute("PING")
        return response in {b"PONG", "PONG"}

    async def get(self, key: str) -> bytes | None:
        response = await self._execute("GET", key)
        if response is None:
            return None
        if isinstance(response, str):
            return response.encode("utf-8")
        return response

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        args: list[str] = ["SET", key, value]
        if ex is not None:
            args.extend(["EX", str(ex)])
        if nx:
            args.append("NX")
        response = await self._execute(*args)
        return response in {b"OK", "OK"}

    async def delete(self, key: str) -> int:
        response = await self._execute("DEL", key)
        if isinstance(response, int):
            return response
        raise RedisClientError("Unexpected DEL response type")

    async def exists(self, key: str) -> bool:
        response = await self._execute("EXISTS", key)
        if isinstance(response, int):
            return response > 0
        raise RedisClientError("Unexpected EXISTS response type")

    async def llen(self, key: str) -> int:
        response = await self._execute("LLEN", key)
        if isinstance(response, int):
            return response
        raise RedisClientError("Unexpected LLEN response type")

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        response = await self._execute("LRANGE", key, str(start), str(stop))
        if response is None:
            return []
        if isinstance(response, list):
            return [self._to_string(item) for item in response]
        raise RedisClientError("Unexpected LRANGE response type")

    async def rpush(self, key: str, value: str) -> int:
        response = await self._execute("RPUSH", key, value)
        if isinstance(response, int):
            return response
        raise RedisClientError("Unexpected RPUSH response type")

    async def aclose(self) -> None:
        async with self._lock:
            await self._close_no_lock()

    async def _execute(self, *args: str):
        async with self._lock:
            return await self._execute_locked(*args)

    async def _execute_locked(self, *args: str):
        try:
            await self._ensure_connected_locked()
            return await self._send_and_read_locked(*args)
        except Exception:
            await self._close_no_lock()
            try:
                await self._ensure_connected_locked()
                return await self._send_and_read_locked(*args)
            except Exception as err:
                await self._close_no_lock()
                raise RedisClientError(str(err)) from err

    async def _ensure_connected_locked(self) -> None:
        if self._writer and not self._writer.is_closing() and self._reader is not None:
            return

        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port, ssl=self._ssl),
            timeout=self._timeout,
        )

        if self._password:
            auth_resp = await self._send_and_read_locked("AUTH", self._password)
            if auth_resp not in {b"OK", "OK"}:
                raise RedisClientError("AUTH failed")

        if self._db:
            select_resp = await self._send_and_read_locked("SELECT", str(self._db))
            if select_resp not in {b"OK", "OK"}:
                raise RedisClientError("SELECT failed")

    async def _send_and_read_locked(self, *args: str):
        if self._writer is None or self._reader is None:
            raise RedisClientError("Redis connection is not initialized")

        payload = self._build_payload(args)
        self._writer.write(payload)
        await asyncio.wait_for(self._writer.drain(), timeout=self._timeout)
        return await self._read_response_locked()

    async def _read_response_locked(self):
        if self._reader is None:
            raise RedisClientError("Redis reader is not initialized")

        first = await asyncio.wait_for(self._reader.readexactly(1), timeout=self._timeout)
        prefix = first.decode("utf-8")

        if prefix == "+":
            line = await asyncio.wait_for(self._reader.readline(), timeout=self._timeout)
            return line.rstrip(b"\r\n")

        if prefix == "-":
            line = await asyncio.wait_for(self._reader.readline(), timeout=self._timeout)
            raise RedisClientError(line.rstrip(b"\r\n").decode("utf-8", errors="ignore"))

        if prefix == ":":
            line = await asyncio.wait_for(self._reader.readline(), timeout=self._timeout)
            return int(line.rstrip(b"\r\n"))

        if prefix == "$":
            line = await asyncio.wait_for(self._reader.readline(), timeout=self._timeout)
            length = int(line.rstrip(b"\r\n"))
            if length == -1:
                return None
            data = await asyncio.wait_for(self._reader.readexactly(length), timeout=self._timeout)
            crlf = await asyncio.wait_for(self._reader.readexactly(2), timeout=self._timeout)
            if crlf != b"\r\n":
                raise RedisClientError("Invalid bulk string termination")
            return data

        if prefix == "*":
            line = await asyncio.wait_for(self._reader.readline(), timeout=self._timeout)
            count = int(line.rstrip(b"\r\n"))
            if count == -1:
                return None
            items = []
            for _ in range(count):
                items.append(await self._read_response_locked())
            return items

        raise RedisClientError(f"Unsupported Redis response prefix: {prefix}")

    async def _close_no_lock(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

        self._reader = None
        self._writer = None

    @staticmethod
    def _build_payload(args: tuple[str, ...]) -> bytes:
        chunks = [f"*{len(args)}\r\n".encode("utf-8")]
        for arg in args:
            data = arg.encode("utf-8")
            chunks.append(f"${len(data)}\r\n".encode("utf-8"))
            chunks.append(data + b"\r\n")
        return b"".join(chunks)

    @staticmethod
    def _to_string(value) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)
