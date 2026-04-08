from datetime import datetime, timedelta, timezone

import jwt

from shared.config.config import JWT_SECRET
from shared.utils.logging_utils import log_function_call, setup_logger

logger = setup_logger("utils.jwtencoder", "utils.log")

class JWTEncoder:
    def __init__(
        self,
        secret: str = JWT_SECRET,
        algorithm: str = "HS256",
        expire_minutes: int = 262800,
    ):
        self.secret = secret
        self.algorithm = algorithm
        self.expire_minutes = expire_minutes
        
    @log_function_call(logger)
    def encode(self, data: dict) -> str:
        to_encode = data.copy()
        to_encode.update({"exp": datetime.now(timezone.utc) + timedelta(minutes=self.expire_minutes)})
        return jwt.encode(to_encode, self.secret, algorithm=self.algorithm)

    @log_function_call(logger)
    def decode(self, token: str) -> dict:
        data = jwt.decode(token, self.secret, algorithms=[self.algorithm])
        return data
