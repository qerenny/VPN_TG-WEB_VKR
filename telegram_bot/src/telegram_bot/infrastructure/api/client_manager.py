import httpx
import traceback
from urllib.parse import quote

from shared.config.config import API_SERVERS, build_inbound_api_base
from shared.infrastructure.users.telegram_user_repository import (
    TelegramUserRepository,
    TelegramUserSnapshot,
)
from shared.infrastructure.vpn_topology_service import VpnTopologyService
from shared.product_constants import PRODUCT_SCOPE_STANDARD
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.infrastructure.api.api_connection import APIConnection
from telegram_bot.shared.utils.json_builder import JSONBuilder
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator

from .json.post_user import build_client_template


class ClientManager:
    def __init__(
        self,
        repo: TelegramUserRepository,
        timestamp: TimestampUtils,
        jsonutils: JSONBuilder,
        uuidgen: UUIDGenerator,
        topology_service: VpnTopologyService | None = None,
    ):
        self.repo = repo
        self.timestamp = timestamp
        self.jsonutils = jsonutils
        self.uuidgen = uuidgen
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}
        self.topology_service = topology_service

    @staticmethod
    def _build_inbound_email(base_email: str, inbound_id: int) -> str:
        """Build per-inbound email/remark suffix in a stable format: name_1, name_2."""
        return f"{base_email}_{inbound_id}"

    @staticmethod
    def _normalize_inbound_ids(raw_inbound_ids) -> list[int]:
        if isinstance(raw_inbound_ids, list):
            return [int(inbound_id) for inbound_id in raw_inbound_ids]
        return [int(raw_inbound_ids)]

    @staticmethod
    def _is_empty_client_id_error(response_data: dict) -> bool:
        message = str(response_data.get("msg", "")).strip().lower()
        return "empty client id" in message

    @staticmethod
    def _extract_duplicate_email(response_data: dict) -> str | None:
        message = str(response_data.get("msg", "")).strip()
        marker = "duplicate email:"
        lower_message = message.lower()
        marker_index = lower_message.find(marker)
        if marker_index == -1:
            return None

        duplicate_email = message[marker_index + len(marker) :].strip()
        return duplicate_email.rstrip(")").strip() or None

    @classmethod
    def _is_expected_duplicate_email_error(
        cls,
        response_data: dict,
        expected_emails: set[str],
    ) -> bool:
        duplicate_email = cls._extract_duplicate_email(response_data)
        return duplicate_email in expected_emails if duplicate_email else False

    async def _process_on_server_pool(
        self,
        handler_func,
        *,
        server_pool: dict[str, dict],
        cache_namespace: str,
    ):
        """Process a handler function on all configured servers in the selected pool."""
        errors = []

        for server_name, server_config in server_pool.items():
            api = None
            try:
                logger.info(f"Processing server: {server_name}")

                api = APIConnection(
                    server_name,
                    server_pool=server_pool,
                    cache_namespace=cache_namespace,
                )
                session = await api.login()
                inbound_url = build_inbound_api_base(server_config)

                # Ensure inbound_ids is a list
                inbound_ids = self._normalize_inbound_ids(server_config["inbound_id"])

                await handler_func(
                    session=session,
                    inbound_url=inbound_url,
                    server_name=server_name,
                    inbound_ids=inbound_ids,
                )

            except Exception as e:
                error_msg = f"Error processing server {server_name}: {str(e)}"
                logger.error(error_msg)
                logger.error(f"Full traceback for {server_name}: {traceback.format_exc()}")
                errors.append(error_msg)
            finally:
                if api:
                    api.release()
        
        if errors:
            raise Exception(f"Errors occurred on servers: {'; '.join(errors)}")

    async def _process_on_all_servers(self, handler_func):
        """Process a handler function on all configured standard servers."""
        await self._process_on_server_pool(
            handler_func,
            server_pool=API_SERVERS,
            cache_namespace="standard",
        )

    async def add_scoped_client(
        self,
        *,
        server_pool: dict[str, dict],
        cache_namespace: str,
        tg_id: int,
        client_uuid: str,
        email: str,
        sub_id: str,
        expires_at: int,
        total_bytes: int = 0,
    ) -> None:
        async def handler(
            session: httpx.AsyncClient,
            inbound_url: str,
            server_name: str,
            inbound_ids: list[int],
        ):
            try:
                expected_emails = {
                    self._build_inbound_email(email, inbound_id)
                    for inbound_id in inbound_ids
                }
                for inbound_id in inbound_ids:
                    current_email = self._build_inbound_email(email, inbound_id)
                    client_template = build_client_template(inbound_id)
                    data = self.jsonutils.update_post_client_json(
                        tg_id,
                        client_template,
                        client_uuid,
                        current_email,
                        expires_at,
                        sub_id,
                        total_bytes=total_bytes,
                    )
                    url = inbound_url + "addClient"
                    logger.info(
                        f"[{server_name}] Sending scoped POST to {url} "
                        f"(Inbound ID: {inbound_id}, total_bytes={total_bytes})"
                    )
                    response = await session.post(url, headers=self.headers, json=data)
                    response.raise_for_status()

                    response_data = response.json()
                    if not response_data.get("success", True):
                        if self._is_expected_duplicate_email_error(
                            response_data,
                            expected_emails,
                        ):
                            logger.warning(
                                f"[{server_name}] Duplicate scoped email returned for "
                                f"tg_id={tg_id}; treating as already provisioned."
                            )
                            continue
                        raise Exception(
                            f"[{server_name}] API responded with error: {response_data}"
                        )
            except Exception as err:
                logger.error(f"[{server_name}] Error in add_scoped_client handler: {err}")
                raise

        await self._process_on_server_pool(
            handler,
            server_pool=server_pool,
            cache_namespace=cache_namespace,
        )

    async def update_scoped_client(
        self,
        *,
        server_pool: dict[str, dict],
        cache_namespace: str,
        tg_id: int,
        client_uuid: str,
        email: str,
        sub_id: str,
        expires_at: int,
        total_bytes: int,
    ) -> None:
        async def handler(
            session: httpx.AsyncClient,
            inbound_url: str,
            server_name: str,
            inbound_ids: list[int],
        ):
            try:
                expected_emails = {
                    self._build_inbound_email(email, inbound_id)
                    for inbound_id in inbound_ids
                }
                for inbound_id in inbound_ids:
                    current_email = self._build_inbound_email(email, inbound_id)
                    client_template = build_client_template(inbound_id)
                    data = self.jsonutils.update_post_client_json(
                        tg_id,
                        client_template,
                        client_uuid,
                        current_email,
                        expires_at,
                        sub_id,
                        total_bytes=total_bytes,
                    )
                    url = inbound_url + f"updateClient/{client_uuid}"
                    logger.info(
                        f"[{server_name}] Sending scoped update to {url} "
                        f"(Inbound ID: {inbound_id}, total_bytes={total_bytes})"
                    )
                    response = await session.post(url, headers=self.headers, json=data)
                    response.raise_for_status()
                    response_data = response.json()
                    if not response_data.get("success", True):
                        if self._is_empty_client_id_error(response_data):
                            fallback_url = inbound_url + "addClient"
                            logger.warning(
                                f"[{server_name}] Scoped update returned empty client ID for "
                                f"uuid={client_uuid}; falling back to scoped addClient"
                            )
                            fallback_response = await session.post(
                                fallback_url,
                                headers=self.headers,
                                json=data,
                            )
                            fallback_response.raise_for_status()
                            fallback_data = fallback_response.json()
                            if fallback_data.get("success", True):
                                continue
                            if self._is_expected_duplicate_email_error(
                                fallback_data,
                                expected_emails,
                            ):
                                logger.warning(
                                    f"[{server_name}] Duplicate scoped email returned during fallback add "
                                    f"for tg_id={tg_id}; treating as already provisioned."
                                )
                                continue
                            raise Exception(
                                f"[{server_name}] API responded with error during fallback add: {fallback_data}"
                            )
                        raise Exception(
                            f"[{server_name}] API responded with error: {response_data}"
                        )
            except Exception as err:
                logger.error(f"[{server_name}] Error in update_scoped_client handler: {err}")
                raise

        await self._process_on_server_pool(
            handler,
            server_pool=server_pool,
            cache_namespace=cache_namespace,
        )

    async def get_scoped_client_usage_bytes(
        self,
        *,
        server_pool: dict[str, dict],
        cache_namespace: str,
        email: str,
    ) -> int:
        total_usage_bytes = 0
        errors = []

        for server_name, server_config in server_pool.items():
            api = None
            try:
                api = APIConnection(
                    server_name,
                    server_pool=server_pool,
                    cache_namespace=cache_namespace,
                )
                session = await api.login()
                inbound_url = build_inbound_api_base(server_config)
                inbound_ids = server_config["inbound_id"]
                if not isinstance(inbound_ids, list):
                    inbound_ids = [inbound_ids]

                for inbound_id in inbound_ids:
                    current_email = self._build_inbound_email(email, int(inbound_id))
                    encoded_email = quote(current_email, safe="")
                    url = inbound_url + f"getClientTraffics/{encoded_email}"
                    response = await session.get(url, headers=self.headers)
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    response_data = response.json()
                    if not response_data.get("success", True):
                        raise Exception(
                            f"[{server_name}] API responded with error: {response_data}"
                        )
                    total_usage_bytes += self._extract_usage_bytes(response_data)
            except Exception as err:
                logger.error(
                    f"[{server_name}] Error in get_scoped_client_usage_bytes handler: {err}"
                )
                errors.append(f"Error processing server {server_name}: {err}")
            finally:
                if api:
                    api.release()

        if errors:
            raise Exception(f"Errors occurred on servers: {'; '.join(errors)}")
        return int(total_usage_bytes)

    async def add_client(
        self,
        tg_id: int,
        period: str,
        user: TelegramUserSnapshot | None = None,
        *,
        target_expiration_date: int | None = None,
    ) -> None:
        """Add a client to all servers."""

        current_user = user or await self.repo.get(tg_id)
        if not current_user:
            raise ValueError(f"User {tg_id} not found")

        uuid = current_user.uuid
        email = current_user.email
        sub_id = current_user.sub_id

        # Set new expiration date once. In stale-client recovery flows we may
        # already know the exact target date we want to preserve.
        date = (
            int(target_expiration_date)
            if target_expiration_date is not None
            else self.timestamp.set_client_date(period)
        )

        async def handler(
            session: httpx.AsyncClient,
            inbound_url: str,
            server_name: str,
            inbound_ids: list[int],
        ):
            try:
                expected_emails = {
                    self._build_inbound_email(email, inbound_id)
                    for inbound_id in inbound_ids
                }
                for inbound_id in inbound_ids:
                    current_email = self._build_inbound_email(email, inbound_id)

                    client_template = build_client_template(inbound_id)
                    data = self.jsonutils.update_post_client_json(
                        tg_id, client_template, uuid, current_email, date, sub_id
                    )

                    url = inbound_url + "addClient"
                    logger.info(
                        f"[{server_name}] Sending POST to {url} (Inbound ID: {inbound_id})"
                    )
                    logger.debug(f"[{server_name}] Payload: {data}")

                    try:
                        response = await session.post(
                            url, headers=self.headers, json=data
                        )
                        response.raise_for_status()
                    except httpx.TimeoutException:
                        raise Exception(
                            f"[{server_name}] Timeout when contacting {url}"
                        )
                    except httpx.RequestError as e:
                        raise Exception(f"[{server_name}] Request failed: {str(e)}")
                    except httpx.HTTPStatusError as e:
                        raise Exception(
                            f"[{server_name}] HTTP error: {e.response.status_code} - {e.response.text}"
                        )

                    try:
                        response_data = response.json()
                        logger.debug(
                            f"[{server_name}] Response JSON: {response_data}"
                        )
                    except Exception:
                        raise Exception(
                            f"[{server_name}] Failed to decode JSON response: {response.text}"
                        )

                    if not response_data.get("success", True):
                        if self._is_expected_duplicate_email_error(
                            response_data,
                            expected_emails,
                        ):
                            logger.warning(
                                f"[{server_name}] Duplicate email returned for known "
                                f"user add on tg_id={tg_id}; treating as already "
                                f"provisioned. Response: {response_data}"
                            )
                            continue
                        raise Exception(
                            f"[{server_name}] API responded with error: {response_data}"
                        )

                    logger.info(
                        f"[{server_name}] Client added successfully for tg_id={tg_id}, inbound_id={inbound_id}"
                    )

            except Exception as e:
                logger.error(f"[{server_name}] Error in add_client handler: {str(e)}")
                raise

        # Call all servers
        await self._process_on_all_servers(handler)

        # Update expiration in database only after all API calls succeed
        await self.repo.update_expiration(expiration_date=date, tg_id=tg_id)
        await self._sync_v2_topology(current_user)
    async def client_exists(self, uuid: str) -> bool:
        """Check if client exists on any server."""

        errors = []

        for server_name, server_config in API_SERVERS.items():
            api = None
            url = ""
            try:
                logger.info(f"Processing server: {server_name}")
                api = APIConnection(server_name)
                session = await api.login()
                inbound_url = build_inbound_api_base(server_config)
                url = inbound_url + f"getClientTrafficsById/{uuid}"
                logger.info(f"[{server_name}] Sending GET to {url}")
                response = await session.get(url, headers=self.headers)
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                    except Exception:
                        errors.append(
                            f"[{server_name}] Failed to decode JSON response: {response.text}"
                        )
                        continue
                    if response_data.get("success", False):
                        return True
                    continue
                if response.status_code not in {404}:
                    errors.append(
                        f"[{server_name}] HTTP error: {response.status_code} - {response.text}"
                    )
            except httpx.TimeoutException:
                errors.append(f"[{server_name}] Timeout when contacting {url}")
            except httpx.RequestError as e:
                errors.append(f"[{server_name}] Request failed: {str(e)}")
            finally:
                if api:
                    api.release()

        if errors:
            raise Exception(f"Errors occurred on servers: {'; '.join(errors)}")
        return False
    async def delete_client(self, uuid: str) -> None:
        """Delete a client from all servers."""

        async def handler(
            session: httpx.AsyncClient,
            inbound_url: str,
            server_name: str,
            inbound_ids: list[int],
        ):
            for inbound_id in inbound_ids:
                try:
                    url = inbound_url + f"{inbound_id}/delClient/{uuid}"
                    logger.info(f"[{server_name}] Sending POST to {url}")
                    response = await session.post(url, headers=self.headers)
                    response.raise_for_status()
                except httpx.TimeoutException:
                    raise Exception(f"[{server_name}] Timeout when contacting {url}")
                except httpx.RequestError as e:
                    raise Exception(f"[{server_name}] Request failed: {str(e)}")
                except httpx.HTTPStatusError as e:
                    raise Exception(
                        f"[{server_name}] HTTP error: {e.response.status_code} - {e.response.text}"
                    )

        await self._process_on_all_servers(handler)

    async def delete_scoped_client(
        self,
        *,
        server_pool: dict[str, dict],
        cache_namespace: str,
        client_uuid: str,
    ) -> None:
        """Delete a client from the selected scoped server pool."""

        async def handler(
            session: httpx.AsyncClient,
            inbound_url: str,
            server_name: str,
            inbound_ids: list[int],
        ):
            for inbound_id in inbound_ids:
                try:
                    url = inbound_url + f"{inbound_id}/delClient/{client_uuid}"
                    logger.info(f"[{server_name}] Sending scoped POST to {url}")
                    response = await session.post(url, headers=self.headers)
                    response.raise_for_status()
                except httpx.TimeoutException:
                    raise Exception(f"[{server_name}] Timeout when contacting {url}")
                except httpx.RequestError as e:
                    raise Exception(f"[{server_name}] Request failed: {str(e)}")
                except httpx.HTTPStatusError as e:
                    raise Exception(
                        f"[{server_name}] HTTP error: {e.response.status_code} - {e.response.text}"
                    )

        await self._process_on_server_pool(
            handler,
            server_pool=server_pool,
            cache_namespace=cache_namespace,
        )
    async def update_client(
        self,
        tg_id: int,
        period: str,
        user: TelegramUserSnapshot | None = None,
    ) -> None:
        """Update a client on all servers."""
        current_user = user or await self.repo.get(tg_id)
        if not current_user:
            raise ValueError(f"User {tg_id} not found")

        uuid = str(current_user.uuid or "").strip()
        if not uuid:
            raise ValueError(f"User {tg_id} has empty uuid; cannot update client")
        email = current_user.email
        old_date = current_user.expiration_date
        sub_id = str(current_user.sub_id or "").strip()

        # Calculate new expiration date only once to avoid multiplying the
        # subscription period by the number of servers.
        date = self.timestamp.update_client_date(old_date, period)

        async def handler(
            session: httpx.AsyncClient,
            inbound_url: str,
            server_name: str,
            inbound_ids: list[int],
        ):
            try:
                for inbound_id in inbound_ids:
                    current_email = self._build_inbound_email(email, inbound_id)
                    client_template = build_client_template(inbound_id)
                    data = self.jsonutils.update_post_client_json(
                        tg_id, client_template, uuid, current_email, date, sub_id
                    )

                    url = inbound_url + f"updateClient/{uuid}"
                    logger.info(
                        f"[{server_name}] Sending POST to {url} (Inbound ID: {inbound_id})"
                    )
                    logger.debug(f"[{server_name}] Payload: {data}")

                    try:
                        response = await session.post(
                            url, headers=self.headers, json=data
                        )
                        response.raise_for_status()
                    except httpx.TimeoutException:
                        raise Exception(
                            f"[{server_name}] Timeout when contacting {url}"
                        )
                    except httpx.RequestError as e:
                        raise Exception(f"[{server_name}] Request failed: {str(e)}")
                    except httpx.HTTPStatusError as e:
                        raise Exception(
                            f"[{server_name}] HTTP error: {e.response.status_code} - {e.response.text}"
                        )

                    try:
                        response_data = response.json()
                        logger.debug(
                            f"[{server_name}] Response JSON: {response_data}"
                        )
                    except Exception:
                        raise Exception(
                            f"[{server_name}] Failed to decode JSON response: {response.text}"
                        )

                    if response_data.get("success", True):
                        logger.info(
                            f"[{server_name}] Client updated successfully for "
                            f"tg_id={tg_id}, inbound_id={inbound_id}, client_id={uuid}"
                        )
                        continue

                    if self._is_empty_client_id_error(response_data):
                        raise ValueError(
                            f"[{server_name}] Cannot update client: panel returned "
                            f"'empty client ID' for tg_id={tg_id}, inbound_id={inbound_id}, "
                            f"uuid={uuid}. Verify that user's uuid matches client id in 3x-ui."
                        )

                    raise Exception(
                        f"[{server_name}] API responded with error: {response_data}"
                    )

            except Exception as e:
                logger.error(f"[{server_name}] Error in update_client handler: {str(e)}")
                raise

        # Execute API calls on all servers using the same calculated expiration date
        await self._process_on_all_servers(handler)

        # Update expiration date in the database once after all servers succeed
        await self.repo.update_expiration(expiration_date=date, tg_id=tg_id)
        await self._sync_v2_topology(current_user)

    async def _sync_v2_topology(self, user: TelegramUserSnapshot) -> None:
        if self.topology_service is None:
            return
        try:
            vpn_client_id = await self.repo.get_standard_vpn_client_id(int(user.tg_id))
            if vpn_client_id is None:
                logger.warning(
                    "Skipped topology sync because standard vpn_client was not found "
                    f"for tg_id={getattr(user, 'tg_id', None)}"
                )
                return
            await self.topology_service.sync_vpn_client_deployments(
                int(vpn_client_id),
                scope=PRODUCT_SCOPE_STANDARD,
            )
        except Exception as err:
            logger.error(
                "Topology sync failed in client manager "
                f"for tg_id={getattr(user, 'tg_id', None)}: {err!r}"
            )

    async def sync_v2_scoped_topology(self, *, vpn_client_id: int, scope: str) -> None:
        if self.topology_service is None:
            return
        try:
            await self.topology_service.sync_vpn_client_deployments(
                int(vpn_client_id),
                scope=str(scope),
            )
        except Exception as err:
            logger.error(
                "Scoped topology dual write failed in client manager "
                f"for vpn_client_id={vpn_client_id}, scope={scope}: {err!r}"
            )

    @classmethod
    def _extract_usage_bytes(cls, response_data: dict) -> int:
        payload = response_data.get("obj", response_data)
        return cls._extract_usage_bytes_from_obj(payload)

    @classmethod
    def _extract_usage_bytes_from_obj(cls, payload) -> int:
        if isinstance(payload, list):
            return sum(cls._extract_usage_bytes_from_obj(item) for item in payload)
        if not isinstance(payload, dict):
            return 0
        if "up" in payload or "down" in payload:
            return int(payload.get("up", 0) or 0) + int(payload.get("down", 0) or 0)
        if "obj" in payload:
            return cls._extract_usage_bytes_from_obj(payload.get("obj"))
        return 0
