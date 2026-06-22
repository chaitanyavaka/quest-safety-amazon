import os
from pathlib import Path

import requests
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env", override=False)

LWA_ENDPOINT = "https://api.amazon.com/auth/o2/token"
SP_API_SANDBOX_BASE_URL = "https://sandbox.sellingpartnerapi-na.amazon.com"
DEFAULT_MARKETPLACE_ID = "ATVPDKIKX0DER"


def get_marketplace_id() -> str:
    return os.getenv("MARKETPLACE_ID", DEFAULT_MARKETPLACE_ID)


def use_live_sandbox_api() -> bool:
    return os.getenv("USE_AMAZON_SANDBOX_API", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def has_sp_api_credentials() -> bool:
    return all(
        os.getenv(key)
        for key in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")
    )


def get_lwa_access_token() -> str:
    if not has_sp_api_credentials():
        raise RuntimeError(
            "Missing CLIENT_ID, CLIENT_SECRET, or REFRESH_TOKEN for Amazon sandbox."
        )

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": os.getenv("REFRESH_TOKEN"),
        "client_id": os.getenv("CLIENT_ID"),
        "client_secret": os.getenv("CLIENT_SECRET"),
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    response = requests.post(
        LWA_ENDPOINT,
        data=payload,
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()

    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Amazon LWA response did not include an access token.")

    return token
