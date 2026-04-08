from fastapi import HTTPException, status
from jwt import PyJWTError

from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.jwt_encoder import JWTEncoder


class UserManagerService:
    def __init__(self, repo: TelegramUserRepository, jwt_encoder: JWTEncoder):
        self.jwt_encoder = jwt_encoder
        self.repo = repo

    async def get_user_info(self, token: str) -> dict:
        try:
            data = self.jwt_encoder.decode(token)
            tg_id = int(data.get("tg_id"))
            email = str(data.get("email") or "").strip()
            if not tg_id or not email:
                raise ValueError("Missing required fields")
        except HTTPException:
            raise
        except PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token signature or expired",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token format",
            ) from exc

        user = await self.repo.get(tg_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if str(user.email) != email:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email mismatch")

        return {
            "tg_id": int(user.tg_id),
            "email": str(user.email),
            "expiration_date": user.expiration_date,
            "login_date": int(user.login_date),
            "sub_id": str(user.sub_id),
        }
