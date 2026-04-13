import json
from typing import Any, Dict

class JSONBuilder:
    @staticmethod
    def update_post_client_json(
        tg_id: int,
        base_template: Dict[str, Any],
        uuid: str,
        email: str,
        period: int,
        sub_id: str,
        total_bytes: int | None = None,
    ) -> Dict[str, Any]:
        data = json.loads(json.dumps(base_template))
        for client in data["settings"]["clients"]:
            client.update(
                {
                    "id": uuid,
                    "email": email,
                    "tgId": str(tg_id),
                    "expiryTime": period,
                    "subId": sub_id,
                }
            )
            if total_bytes is not None:
                client["totalGB"] = int(total_bytes)

        data["settings"] = json.dumps(data["settings"])
        return data
