import datetime
import hashlib
from typing import Any, Optional

import pydantic
from pydantic import BaseModel
from telebot import types as tg
from telebot.api import ApiHTTPException
from telebot.callback_data import CallbackData
from telebot.types import service as tg_service_types
from telebot_components.language import any_text_to_str
from telebot_components.menu.menu import (
    MenuMechanism,
)
from telebot_components.utils import TextMarkup

from telebot_constructor.user_flow.blocks.base import UserFlowBlock
from telebot_constructor.user_flow.types import (
    SetupResult,
    UserFlowContext,
    UserFlowSetupContext,
)
from telebot_constructor.utils import preprocess_for_telegram, without_nones
from telebot_constructor.utils.pydantic import LocalizableText
from telebot_constructor.utils.store import CachedKeyValueStore


class ButtonActionData(pydantic.BaseModel):
    from_block_id: str
    to_block_id: str


BUTTON_ACTION_CALLBACK_DATA = CallbackData("hash", prefix="action")
NOOP_CALLBACK_DATA = CallbackData(prefix="noop")


class MenuItem(BaseModel):
    label: LocalizableText

    # at most one field must be non-None; if all are None, the item is a noop button
    next_block_id: Optional[str] = None  # for terminal items
    link_url: Optional[str] = None  # for link buttons (works only if mechanism is inline)

    def model_post_init(self, __context: Any) -> None:
        specified_options = [o for o in (self.next_block_id, self.link_url) if o is not None]
        if len(specified_options) > 1:
            raise ValueError("At most one of the options may be specified: submenu, next block, or link URL")
        self._is_noop = len(specified_options) == 0


class MenuConfig(BaseModel):
    mechanism: MenuMechanism
    back_label: LocalizableText | None
    lock_after_termination: bool


class Menu(BaseModel):
    text: LocalizableText
    items: list[MenuItem]
    config: MenuConfig
    markup: TextMarkup = TextMarkup.NONE

    def model_post_init(self, __conext: Any) -> None:
        self.text_preprocessed = preprocess_for_telegram(self.text, self.markup)


class MenuBlock(UserFlowBlock):
    menu: Menu

    def possible_next_block_ids(self) -> list[str]:
        return without_nones([item.next_block_id for item in self.menu.items])

    @property
    def displayed_items(self) -> list[MenuItem]:
        items = self.menu.items.copy()
        if self.menu.config.back_label is not None:
            # FIXME: add "back button" support
            # items.append(MenuItem(label=self.menu.config.back_label, submenu=self.parent_menu))
            pass
        return items

    async def enter(self, context: UserFlowContext) -> None:
        user = context.user
        language = None if self._language_store is None else await self._language_store.get_user_language(context.user)
        updateable_menu_message_id = context.updateable_message_id

        if self.menu.config.mechanism.is_inline_kbd():
            inline_buttons: list[tg.InlineKeyboardButton] = []
            button_actions = dict[str, ButtonActionData]()
            for menu_item in self.displayed_items:
                if menu_item.link_url is not None:
                    inline_buttons.append(
                        tg.InlineKeyboardButton(
                            text=any_text_to_str(menu_item.label, language),
                            url=menu_item.link_url,
                        )
                    )
                elif menu_item.next_block_id is not None:
                    action = ButtonActionData(
                        from_block_id=self.block_id,
                        to_block_id=menu_item.next_block_id,
                    )
                    action_hash = hashlib.md5(action.model_dump_json().encode("utf-8")).hexdigest()
                    button_actions[action_hash] = action
                    inline_buttons.append(
                        tg.InlineKeyboardButton(
                            text=any_text_to_str(menu_item.label, language),
                            callback_data=BUTTON_ACTION_CALLBACK_DATA.new(action_hash),
                        )
                    )
                else:
                    inline_buttons.append(
                        tg.InlineKeyboardButton(
                            text=any_text_to_str(menu_item.label, language),
                            callback_data=NOOP_CALLBACK_DATA.new(),  # type: ignore
                        )
                    )
            reply_markup: tg.ReplyMarkup = tg.InlineKeyboardMarkup(keyboard=[[button] for button in inline_buttons])
            await self._button_action_store.save_multiple(button_actions)
        else:
            reply_markup = tg.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            # HACK: telebot annotates keyboard as list[list[KeyboardButton]], but actually expectes JSONified versions
            # of the button objects
            reply_markup.keyboard = [  # type: ignore
                [tg.KeyboardButton(text=any_text_to_str(item.label, language)).to_dict()]
                for item in self.displayed_items
            ]

        if updateable_menu_message_id is not None and self.menu.config.mechanism.is_updateable():
            try:
                await context.bot.edit_message_text(
                    chat_id=user.id,
                    text=any_text_to_str(self.menu.text_preprocessed, language),
                    parse_mode=self.menu.markup.parse_mode(),
                    message_id=updateable_menu_message_id,
                    reply_markup=reply_markup,
                )
                return
            except ApiHTTPException as e:
                self._logger.info(f"Error editing message text and reply markup, will send a new message: {e!r}")

        await context.bot.send_message(
            chat_id=user.id,
            text=any_text_to_str(self.menu.text_preprocessed, language),
            parse_mode=self.menu.markup.parse_mode(),
            reply_markup=reply_markup,
        )

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        self._logger = context.make_instrumented_logger(__name__, self.block_id)
        self._language_store = context.language_store
        self._button_action_store = CachedKeyValueStore[ButtonActionData](
            name="button-action",
            prefix=context.bot_prefix,
            redis=context.redis,
            dumper=ButtonActionData.model_dump_json,
            loader=ButtonActionData.model_validate_json,
            expiration_time=datetime.timedelta(days=180),
        )

        @context.bot.callback_query_handler(callback_data=BUTTON_ACTION_CALLBACK_DATA, auto_answer=True)
        async def handle_menu(call: tg.CallbackQuery) -> tg_service_types.HandlerResult | None:
            action_hash = BUTTON_ACTION_CALLBACK_DATA.parse(call.data)
            action = await self._button_action_store.load(action_hash)
            if action is None:
                return None
            if action.from_block_id != self.block_id:
                # the button was created by a different menu block and should be handled from there
                return tg_service_types.HandlerResult(continue_to_other_handlers=True)
            await context.enter_block(
                action.to_block_id,
                UserFlowContext.from_setup_context(
                    context,
                    user=call.from_user,
                    chat=None,
                    updateable_message_id=call.message.id if self.menu.config.mechanism.is_updateable() else None,
                    last_update_content=call,
                ),
            )
            return None

        @context.bot.callback_query_handler(callback_data=NOOP_CALLBACK_DATA, auto_answer=True)
        async def handle_noop(call: tg.CallbackQuery) -> tg_service_types.HandlerResult | None:
            return None

        return SetupResult.empty()
