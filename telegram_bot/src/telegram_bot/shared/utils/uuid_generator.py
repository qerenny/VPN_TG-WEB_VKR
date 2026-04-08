# shared/utils/uuid_generator.py

import uuid

from haikunator import Haikunator

from shared.utils.logging_utils import logger


class UUIDGenerator:
    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def generate_email(delimiter: str = "-", token_length: int = 0, token_hex=False) -> str:
        haikunator = Haikunator()
        return haikunator.haikunate(delimiter=delimiter, token_length=token_length, token_hex=token_hex)
