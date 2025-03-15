from typing import Any, Optional

from pydantic import BaseModel
from telebot_components.menu.menu import Menu as ComponentsMenu
from telebot_components.menu.menu import MenuConfig as ComponentsMenuConfig
from telebot_components.menu.menu import (
    MenuHandler,
    MenuMechanism,
    TerminatorContext,
    TerminatorResult,
)
from telebot_components.menu.menu import MenuItem as ComponentsMenuItem
from telebot_components.utils import TextMarkup

from telebot_constructor.user_flow.blocks.base import UserFlowBlock
from telebot_constructor.user_flow.types import (
    SetupResult,
    UserFlowContext,
    UserFlowSetupContext,
)
from telebot_constructor.utils import preprocess_for_telegram, without_nones
from telebot_constructor.utils.pydantic import LocalizableText

NOOP_TERMINATOR = "noop"


class MenuItem(BaseModel):
    label: LocalizableText

    # at most one field must be non-None; if all are None, the item is a noop button
    submenu: Optional["Menu"] = None
    next_block_id: Optional[str] = None  # for terminal items
    link_url: Optional[str] = None  # for link buttons (works only if mechanism is inline)

    def model_post_init(self, __context: Any) -> None:
        specified_options = [o for o in (self.submenu, self.next_block_id, self.link_url) if o is not None]
        if len(specified_options) > 1:
            raise ValueError("At most one of the options may be specified: submenu, next block, or link URL")
        self._is_noop = len(specified_options) == 0

    def to_components_menu_item(self) -> ComponentsMenuItem:
        return ComponentsMenuItem(
            label=self.label,
            submenu=None if self.submenu is None else self.submenu.to_components_menu(),
            terminator=NOOP_TERMINATOR if self._is_noop else self.next_block_id,
            link_url=self.link_url,
            bound_category=None,
        )


class MenuConfig(BaseModel):
    mechanism: MenuMechanism
    back_label: Optional[LocalizableText]
    lock_after_termination: bool


class Menu(BaseModel):
    text: LocalizableText
    items: list[MenuItem]
    config: MenuConfig
    markup: TextMarkup = TextMarkup.NONE

    def to_components_menu(self) -> ComponentsMenu:
        config = ComponentsMenuConfig(
            back_label=self.config.back_label,
            lock_after_termination=self.config.lock_after_termination,
            mechanism=self.config.mechanism,
            text_markup=self.markup,
        )
        return ComponentsMenu(
            text=preprocess_for_telegram(self.text, self.markup),
            menu_items=[item.to_components_menu_item() for item in self.items],
            config=config,
        )


class MenuBlock(UserFlowBlock):
    """Multilevel menu block powered by Telegram inline buttons"""

    menu: Menu

    def possible_next_block_ids(self) -> list[str]:
        return without_nones([item.next_block_id for item in self.menu.items])

    def model_post_init(self, __context: Any) -> None:
        self.validate_menu()

    def validate_menu(self) -> None:
        self.menu.to_components_menu()  # telebot_components' menu performs validation on instantiation

    @property
    def menu_handler(self) -> MenuHandler:
        if self._components_menu_handler is None:
            raise RuntimeError("self.menu_handler called before setup method")
        return self._components_menu_handler

    async def enter(self, context: UserFlowContext) -> None:
        await self.menu_handler.start_menu(bot=context.bot, user=context.user)

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        self._components_menu = self.menu.to_components_menu()
        self._components_menu_handler = MenuHandler(
            name=self.block_id,
            bot_prefix=context.bot_prefix,
            menu_tree=self._components_menu,
            redis=context.redis,
            category_store=None,
            language_store=context.language_store,
        )
        context.errors_store.instrument(self._components_menu_handler.logger)

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

        self.menu_handler.setup(
            bot=context.bot,
            on_terminal_menu_option_selected=on_terminal_menu_option_selected,
        )
        return SetupResult.empty()
