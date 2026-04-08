from shared.config.config import INBOUND_AMOUNT_OF_DEVICES

def build_client_template(inbound_id: int):
    """
    Builds a template for the client configuration.
    
    Returns:
        dict: A dictionary containing the client template.
    """
    client_template = {
    "id": inbound_id,
    "settings": {
        "clients": [
            {
                "id": None,
                "flow": "xtls-rprx-vision",
                "email": None,
                "limitIp": INBOUND_AMOUNT_OF_DEVICES,
                "totalGB": 0,
                "expiryTime": 0,
                "enable": True,
                "tgId": None,
                "subId": None,
                "reset": 0,
                }
            ]
        },
    }
    return client_template
