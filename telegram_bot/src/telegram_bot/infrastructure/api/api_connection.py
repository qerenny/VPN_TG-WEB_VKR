import asyncio
import httpx
import time
from typing import Optional

from shared.config.config import API_SERVERS, build_base_url
from shared.utils.logging_utils import logger, retry_on_error


class APIConnection:
    SESSION_CACHE_TTL_SECONDS = 10 * 60
    REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=20.0)
    _session_pool: dict[str, tuple[httpx.AsyncClient, float]] = {}
    _session_locks: dict[str, asyncio.Lock] = {}

    def __init__(
        self,
        server_name: str,
        *,
        server_pool: dict[str, dict] | None = None,
        cache_namespace: str = "standard",
    ):
        active_pool = server_pool or API_SERVERS
        if server_name not in active_pool:
            raise ValueError(f"Unknown server name: {server_name}")
        self.server_name = server_name
        self.server_config = active_pool[server_name]
        self.cache_key = f"{cache_namespace}:{server_name}"
        self.base_url = build_base_url(self.server_config)
        self.session: Optional[httpx.AsyncClient] = None

    @classmethod
    def _get_server_lock(cls, cache_key: str) -> asyncio.Lock:
        lock = cls._session_locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            cls._session_locks[cache_key] = lock
        return lock

    @staticmethod
    async def _safe_close(session: httpx.AsyncClient) -> None:
        try:
            await session.aclose()
        except Exception as err:
            logger.warning(f"Failed to close API session cleanly: {err}")

    @retry_on_error(retries=3, delay=5)
    async def login(self) -> httpx.AsyncClient:
        lock = self._get_server_lock(self.cache_key)
        async with lock:
            now = time.monotonic()
            cached = self._session_pool.get(self.cache_key)
            if cached is not None:
                session, expires_at = cached
                if now < expires_at and not getattr(session, "is_closed", False):
                    self.session = session
                    logger.info(f"Reusing cached API session for {self.server_name}")
                    return session

                self._session_pool.pop(self.cache_key, None)
                await self._safe_close(session)

            new_session = httpx.AsyncClient(
                verify=False,
                timeout=self.REQUEST_TIMEOUT,
            )
            url = f"{self.base_url}/login"
            payload = {
                "username": self.server_config["username"],
                "password": self.server_config["password"],
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            try:
                response = await new_session.post(url, headers=headers, data=payload)
                if response.status_code != 200:
                    logger.error(
                        f"Login failed for {url}: {response.status_code} - {response.text}"
                    )
                    raise Exception("Failed to login to API")
            except Exception:
                await self._safe_close(new_session)
                raise

            self._session_pool[self.cache_key] = (
                new_session,
                time.monotonic() + self.SESSION_CACHE_TTL_SECONDS,
            )
            self.session = new_session
            logger.info(
                f"Successfully logged in to API for {self.server_name}; session cached for "
                f"{self.SESSION_CACHE_TTL_SECONDS} seconds"
            )
            return new_session

    def release(self) -> None:
        self.session = None

    async def logout(self):
        if not self.session:
            return

        lock = self._get_server_lock(self.cache_key)
        async with lock:
            cached = self._session_pool.get(self.cache_key)
            if cached and cached[0] is self.session:
                self._session_pool.pop(self.cache_key, None)

            await self._safe_close(self.session)
            logger.info("Successfully logged out of API")
            self.session = None
