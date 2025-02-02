"""Convert backend's pydantic types to JSON schema or validate that the existing JSON schema is up-to-date"""

import argparse
import json
import sys
from pathlib import Path

import dictdiffer  # type: ignore
from pydantic import BaseModel
from pydantic._internal._core_utils import CoreSchemaOrField
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue

from telebot_constructor.app_models import (
    BotErrorsPage,
    BotInfo,
    BotTokenValidationResult,
    BotVersionsPage,
    FormInfo,
    FormInfoBasic,
    FormResultsPage,
    LoggedInUser,
    SaveBotConfigVersionPayload,
    SetAlertChatIdPayload,
    StartBotPayload,
    TgBotUser,
    TgBotUserUpdate,
    TgGroupChat,
)
from telebot_constructor.bot_config import BotConfig
from telebot_constructor.user_flow.blocks.form import BaseFormFieldConfig
from telebot_constructor.utils.pydantic import LanguageData

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonschema-path", type=Path, default=Path(__file__).parent / "../../data/schema.json")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the current schema with the one file and exit with error status if they differ",
    )

    args = parser.parse_args()

    class CastUnsupportedToNullSchema(GenerateJsonSchema):
        def handle_invalid_for_json_schema(self, schema: CoreSchemaOrField, error_info: str) -> JsonSchemaValue:
            return {"type": "null"}

    class BackendDataModels(BaseModel):
        """Temporary class to pack several models into one schema; not used directly by frontend code"""

        bot_config: BotConfig
        tg_group_chat: TgGroupChat
        tg_bot_user: TgBotUser
        tg_bot_user_update: TgBotUserUpdate
        language_data: LanguageData
        base_form_field_config: BaseFormFieldConfig
        logged_in_user: LoggedInUser
        bot_info: BotInfo
        save_bot_config_version_payload: SaveBotConfigVersionPayload
        start_bot_payload: StartBotPayload
        form_info: FormInfo
        form_info_basic: FormInfoBasic
        form_results_page: FormResultsPage
        bot_errors_page: BotErrorsPage
        bot_versions_page: BotVersionsPage
        alert_chat_id_payload: SetAlertChatIdPayload
        bot_token_validation_result: BotTokenValidationResult

    current_schema = BackendDataModels.model_json_schema(
        mode="serialization",
        schema_generator=CastUnsupportedToNullSchema,
    )

    if not args.check:
        args.jsonschema_path.write_text(json.dumps(current_schema, ensure_ascii=False, indent=2))
    else:
        existing_schema = json.loads(args.jsonschema_path.read_text())
        if existing_schema == current_schema:
            sys.exit()
        diff = list(dictdiffer.diff(existing_schema, current_schema))
        print("JSON schema in the file is out of date, if you have updated Python data model, you must regenerate it")
        print("Diff:")
        print(json.dumps(diff, indent=4, ensure_ascii=False))
        sys.exit(1)
