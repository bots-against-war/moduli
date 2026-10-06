"""Simple script to import bot into constructor from JSON file"""

import argparse
import os
import secrets
import sys
import urllib  # type: ignore
import urllib.parse
from pathlib import Path

import requests  # type: ignore

from telebot_constructor.bot_config import BotConfig

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bot_config", type=Path)
    parser.add_argument("--url", default="http://localhost:8088")
    args = parser.parse_args()

    config = BotConfig.model_validate_json(args.bot_config.read_text())
    print("Config loaded")

    url = str(args.url)

    print("Validating token...")
    token = os.environ["BOT_TOKEN"]
    resp = requests.post(urllib.parse.urljoin(url, "/api/validate-token"), json={"token": token})
    if resp.status_code == 200:
        print("OK")
    else:
        print(f"Failed to validate token: {resp.text}")
        sys.exit(1)

    bot_id = f"imported-{secrets.token_urlsafe(8)}"
    token_secret_name = f"{bot_id}-token-{secrets.token_urlsafe(4)}"
    print(f"Saving token secret ({token_secret_name})...")
    resp = requests.post(
        urllib.parse.urljoin(url, f"/api/secrets/{urllib.parse.quote(token_secret_name)}?is_token=true"),
        data=token,
    )
    if resp.status_code == 200:
        print("OK")
    else:
        print(f"Failed to save token: {resp.text}")
        sys.exit(1)

    config.token_secret_name = token_secret_name
    print("Saving bot config...")
    requests.post(
        urllib.parse.urljoin(url, f"/api/config/{urllib.parse.quote(bot_id)}"),
        json={
            "config": config.model_dump(mode="json"),
            "start": False,
            "version_message": None,
            "display_name": (config.display_name or "Unknown") + f" (imported from {args.bot_config})",
        },
    )
    if resp.status_code == 200:
        print("OK")
    else:
        print(f"Failed to save config: {resp.text}")
        sys.exit(1)
