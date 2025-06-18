from typing import Any

from pydantic import BaseModel
from telebot import types as tg
from telebot.api import ApiHTTPException
from telebot.callback_data import CallbackData
from telebot.types import constants as tgconst
from telebot.types import service as tgservice
from telebot_components.language import any_text_to_str
from telebot_components.menu.menu import MenuMechanism
from telebot_components.utils import TextMarkup

from telebot_constructor.store.menu import ButtonActionData
from telebot_constructor.user_flow.blocks.base import UserFlowBlock
from telebot_constructor.user_flow.types import (
    MenuBlocksContext,
    SetupResult,
    UserFlowContext,
    UserFlowSetupContext,
)
from telebot_constructor.utils import preprocess_for_telegram, without_nones
from telebot_constructor.utils.pydantic import LocalizableText

BUTTON_ACTION_CALLBACK_DATA = CallbackData("hash", prefix="action")
NOOP_CALLBACK_DATA = CallbackData(prefix="noop")


class MenuItem(BaseModel):
    label: LocalizableText

    # at most one field must be non-None; if all are None, the item is a noop button
    next_block_id: str | None = None
    link_url: str | None = None  # for link buttons (TODO: validate that is used with inline only)

    def model_post_init(self, __context: Any) -> None:
        specified_options = [o for o in (self.next_block_id, self.link_url) if o is not None]
        if len(specified_options) > 1:
            raise ValueError("At most one of the options may be specified: next block or link URL")
        self._is_noop = len(specified_options) == 0

        # especially for reply keyboards we must strip button captions for later text matching
        if isinstance(self.label, str):
            self.label = self.label.strip()
        else:
            self.label = {lang: text.strip() for lang, text in self.label.items()}


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
        self._text_preprocessed = preprocess_for_telegram(self.text, self.markup)


class MenuBlock(UserFlowBlock):
    menu: Menu

    def possible_next_block_ids(self) -> list[str]:
        return without_nones([item.next_block_id for item in self.menu.items])

    def _history_session_id(self, user_id: int, updateable_message_id: int | None) -> str | None:
        if self.menu.config.mechanism.is_updateable():
            if updateable_message_id is not None:
                return f"u{user_id}-m{updateable_message_id}"
            else:
                return None
        else:
            return f"u{user_id}"

    async def enter(self, context: UserFlowContext) -> None:
        user = context.user
        language = None if self._language_store is None else await self._language_store.get_user_language(context.user)
        is_nested_menu = context.menu_blocks_ctx is not None
        updateable_message_id = (
            context.menu_blocks_ctx.updateable_message_id if context.menu_blocks_ctx is not None else None
        )
        history_session_id = self._history_session_id(user.id, updateable_message_id)
        if history_session_id is not None and not is_nested_menu:
            await self._metadata_store.user_history_store.drop(history_session_id)

        can_go_back = (
            is_nested_menu
            and history_session_id is not None
            and (await self._metadata_store.user_history_store.length(history_session_id) > 0)
        )
        if history_session_id is not None:
            await self._metadata_store.user_history_store.push(history_session_id, self.block_id)

        if self.menu.config.mechanism.is_inline_kbd():
            inline_buttons: list[tg.InlineKeyboardButton] = []
            button_actions = dict[str, ButtonActionData]()
            for menu_item in self.menu.items:
                if menu_item.next_block_id is not None:
                    action = ButtonActionData(block_id=self.block_id, route_to_block_id=menu_item.next_block_id)
                    button_actions[action.md5_hash] = action
                    inline_buttons.append(
                        tg.InlineKeyboardButton(
                            text=any_text_to_str(menu_item.label, language),
                            callback_data=BUTTON_ACTION_CALLBACK_DATA.new(action.md5_hash),
                        )
                    )
                elif menu_item.link_url is not None:
                    inline_buttons.append(
                        tg.InlineKeyboardButton(
                            text=any_text_to_str(menu_item.label, language),
                            url=menu_item.link_url,
                        )
                    )
                else:
                    inline_buttons.append(
                        tg.InlineKeyboardButton(
                            text=any_text_to_str(menu_item.label, language),
                            callback_data=NOOP_CALLBACK_DATA.new(),  # type: ignore
                        )
                    )

            if can_go_back and self.menu.config.back_label is not None:
                action = ButtonActionData(block_id=self.block_id, route_to_block_id=None)
                button_actions[action.md5_hash] = action
                inline_buttons.append(
                    tg.InlineKeyboardButton(
                        text=any_text_to_str(self.menu.config.back_label, language),
                        callback_data=BUTTON_ACTION_CALLBACK_DATA.new(action.md5_hash),
                    )
                )

            reply_markup: tg.ReplyMarkup = tg.InlineKeyboardMarkup(keyboard=[[button] for button in inline_buttons])
            await self._metadata_store.button_action_store.save_multiple(button_actions)
        else:
            reply_markup = tg.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for item in self.menu.items:
                reply_markup.add(tg.KeyboardButton(text=any_text_to_str(item.label, language)))
            if self.menu.config.back_label is not None and can_go_back:
                reply_markup.add(tg.KeyboardButton(text=any_text_to_str(self.menu.config.back_label, language)))

        if updateable_message_id is not None and self.menu.config.mechanism.is_updateable():
            try:
                await context.bot.edit_message_text(
                    chat_id=user.id,
                    text=any_text_to_str(self.menu._text_preprocessed, language),
                    parse_mode=self.menu.markup.parse_mode(),
                    message_id=updateable_message_id,
                    reply_markup=reply_markup,
                )
                return
            except ApiHTTPException as e:
                self._logger.info(f"Error editing message text and reply markup, will send a new message: {e!r}")

        new_message = await context.bot.send_message(
            chat_id=user.id,
            text=any_text_to_str(self.menu._text_preprocessed, language),
            parse_mode=self.menu.markup.parse_mode(),
            reply_markup=reply_markup,
        )
        if history_session_id is None:
            if new_history_session_id := self._history_session_id(user.id, new_message.id):
                await self._metadata_store.user_history_store.push(
                    new_history_session_id,
                    self.block_id,
                )

    async def get_back_destination(self, history_id: str) -> str | None:
        # NOTE: to understand why 2 pops are needed, consider two-level menu A->B
        # - user enters A, "A" is pushed into history
        # - user enters B, "B" is pushed into history, which is not ["A", "B"]
        # - user presses "back", to get the destination we need to pop two last elements
        #   and route to the next-to-last, "A"; the history is empty
        # - user enters A and it's pushed back into history
        await self._metadata_store.user_history_store.pop(history_id)
        return await self._metadata_store.user_history_store.pop(history_id)

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        self._logger = context.make_instrumented_logger(__name__, self.block_id)
        self._language_store = context.language_store
        self._metadata_store = context.menu_metadata_store

        @context.bot.callback_query_handler(callback_data=BUTTON_ACTION_CALLBACK_DATA, auto_answer=True)  # type: ignore
        async def handle_inline_menu(call: tg.CallbackQuery) -> tgservice.HandlerResult | None:
            cbk_data = BUTTON_ACTION_CALLBACK_DATA.parse(call.data)
            action = await self._metadata_store.button_action_store.load(cbk_data["hash"])
            if action is None:
                return None
            if action.block_id != self.block_id:
                # the button was created by a different menu block and should be handled from there
                return tgservice.HandlerResult(continue_to_other_handlers=True)

            if action.route_to_block_id is not None:
                next_block_id = action.route_to_block_id
            else:
                history_id = self._history_session_id(call.from_user.id, call.message.id)
                if history_id is None:
                    return None
                maybe_next_block_id = await self.get_back_destination(history_id)
                if maybe_next_block_id is None:
                    return None
                else:
                    next_block_id = maybe_next_block_id
            await context.enter_block(
                next_block_id,
                UserFlowContext.from_setup_context(
                    context,
                    user=call.from_user,
                    chat=None,
                    menu_blocks_ctx=MenuBlocksContext(
                        updateable_message_id=call.message.id if self.menu.config.mechanism.is_updateable() else None,
                    ),
                    last_update_content=call,
                ),
            )
            return None

        @context.bot.message_handler(
            priority=1000,
            chat_types=[tgconst.ChatType.private],
            func=context.active_block_filter(self.block_id),
        )  # type: ignore
        async def maybe_handle_reply_menu(message: tg.Message) -> tgservice.HandlerResult | None:
            passthrough = tgservice.HandlerResult(continue_to_other_handlers=True)
            if self.menu.config.mechanism is not MenuMechanism.REPLY_KEYBOARD:
                return passthrough

            next_block_ctx = UserFlowContext.from_setup_context(
                context,
                user=message.from_user,
                chat=None,
                menu_blocks_ctx=MenuBlocksContext(updateable_message_id=None),
                last_update_content=message,
            )

            for item in self.menu.items:
                if item.next_block_id is None:
                    continue

                item_texts = [item.label] if isinstance(item.label, str) else list(item.label.values())
                for t in item_texts:
                    if message.text == t:
                        await context.enter_block(item.next_block_id, next_block_ctx)
                        return None

            if self.menu.config.back_label is not None:
                back_label = self.menu.config.back_label
                back_texts = [back_label] if isinstance(back_label, str) else list(back_label.values())
                if any(t == message.text for t in back_texts):
                    history_id = self._history_session_id(message.from_user.id, None)
                    if history_id is not None:
                        maybe_next_block_id = await self.get_back_destination(history_id)
                        if maybe_next_block_id is not None:
                            await context.enter_block(maybe_next_block_id, next_block_ctx)

            return passthrough

        @context.bot.callback_query_handler(callback_data=NOOP_CALLBACK_DATA, auto_answer=True)  # type: ignore
        async def handle_noop(call: tg.CallbackQuery) -> tgservice.HandlerResult | None:
            return None

        return SetupResult.empty()
