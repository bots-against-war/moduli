import datetime
from typing import Any, Optional

from pydantic import BaseModel
from telebot import types as tg
from telebot.api import ApiHTTPException
from telebot.callback_data import CallbackData
from telebot_components.language import MaybeLanguage, any_text_to_str
from telebot_components.menu.menu import (
    MenuMechanism,
    TerminatorContext,
    TerminatorResult,
)
from telebot_components.stores.generic import KeyValueStore
from telebot_components.utils import TextMarkup

from telebot_constructor.user_flow.blocks.base import UserFlowBlock
from telebot_constructor.user_flow.types import (
    SetupResult,
    UserFlowContext,
    UserFlowSetupContext,
)
from telebot_constructor.utils import preprocess_for_telegram, without_nones
from telebot_constructor.utils.pydantic import LocalizableText

ROUTE_CALLBACK_DATA = CallbackData("id", prefix="route")
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

    def get_inline_button(self, language: MaybeLanguage):
        if self.link_url is not None:
            return tg.InlineKeyboardButton(
                text=any_text_to_str(self.label, language),
                url=self.link_url,
            )
        elif self.next_block_id is not None:
            return tg.InlineKeyboardButton(
                text=any_text_to_str(self.label, language),
                callback_data=ROUTE_CALLBACK_DATA.new(self.next_block_id),  # type: ignore
            )
        else:
            return tg.InlineKeyboardButton(
                text=any_text_to_str(self.label, language),
                callback_data=NOOP_CALLBACK_DATA.new(),  # type: ignore
            )

    def get_keyboard_button(self, language: MaybeLanguage) -> tg.KeyboardButton:
        return tg.KeyboardButton(text=any_text_to_str(self.label, language))


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
        updateable_menu_message_id = await self._updateable_menu_message_id_store.load(user.id)

        if self.menu.config.mechanism.is_inline_kbd():
            reply_markup: tg.ReplyMarkup = tg.InlineKeyboardMarkup(
                keyboard=[[menu_item.get_inline_button(language)] for menu_item in self.displayed_items]
            )
        else:
            reply_markup = tg.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            # HACK: telebot annotates keyboard as list[list[KeyboardButton]], but actually expectes JSONified versions
            # of the button objects
            reply_markup.keyboard = [[item.get_keyboard_button(language).to_dict()] for item in self.displayed_items]  # type: ignore

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

        new_menu_message = await context.bot.send_message(
            chat_id=user.id,
            text=any_text_to_str(self.menu.text_preprocessed, language),
            parse_mode=self.menu.markup.parse_mode(),
            reply_markup=reply_markup,
        )
        if self.menu.config.mechanism.is_updateable():
            await self._updateable_menu_message_id_store.save(user.id, new_menu_message.id)

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        self._logger = context.make_instrumented_logger(__name__, self.block_id)
        self._language_store = context.language_store

        self._updateable_menu_message_id_store: KeyValueStore[int] = KeyValueStore[int](
            name="last-menu-msg",
            prefix=context.bot_prefix,
            redis=context.redis,
            expiration_time=datetime.timedelta(days=180),
            dumper=str,
            loader=int,
        )

        async def on_terminal_menu_option_selected(terminator_context: TerminatorContext) -> Optional[TerminatorResult]:
            terminator = terminator_context.terminator
            if terminator != NOOP_TERMINATOR:
                next_block_id = terminator
                await context.enter_block(
                    next_block_id,
                    UserFlowContext.from_setup_context(
                        setup_ctx=context,
                        chat=(
                            terminator_context.menu_message.chat
                            if terminator_context.menu_message is not None
                            else None
                        ),
                        user=terminator_context.user,
                        last_update_content=terminator_context.menu_message,
                    ),
                )
            return None

        return SetupResult.empty()
