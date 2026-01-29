import asyncio
import logging
import os

import aiohttp

from telebot_constructor.app_models import SaveBotConfigVersionPayload
from telebot_constructor.client.client import TrustedModuliApiClient, TrustedModuliApiClientConfig


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    async with aiohttp.ClientSession() as session:
        api = TrustedModuliApiClient(
            aiohttp_session=session,
            config=TrustedModuliApiClientConfig(
                base_url=os.environ["MODULI_API_URL"],
                trusted_client_token=os.environ["MODULI_API_TOKEN"],
            ),
        )

        owner = int(os.environ["OWNER_ID"])
        source_bot_id = os.environ["SOURCE_BOT_ID"]
        target_bot_id = os.environ["TARGET_BOT_ID"]

        print(await api.logged_in_user(user=owner))

        source_bot = await api.get_bot_config(user=owner, bot_id=source_bot_id)
        print("Source bot config retrieved")
        target_bot = await api.get_bot_config(user=owner, bot_id=target_bot_id)
        print("Target bot config to be replaced retrieved (will take only token secret name)")

        source_bot.token_secret_name = target_bot.token_secret_name
        source_bot.display_name = target_bot.display_name

        if await api.save_new_bot_config_version(
            user=owner,
            bot_id=target_bot_id,
            payload=SaveBotConfigVersionPayload(
                config=source_bot,
                version_message=f"cloned from {source_bot_id}",
                start=False,
            ),
        ):
            print("OK")


asyncio.run(main())
