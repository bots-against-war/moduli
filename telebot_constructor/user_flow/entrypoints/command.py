import enum

from telebot import types as tg
from telebot.types import constants as tg_const

from telebot_constructor.user_flow.entrypoints.base import UserFlowEntryPoint
from telebot_constructor.user_flow.types import (
    BotCommandInfo,
    SetupResult,
    UserFlowBlockId,
    UserFlowContext,
    UserFlowSetupContext,
)
from telebot_constructor.utils import without_nones


class CommandScope(enum.Enum):
    PRIVATE = "private"
    GROUP = "group"
    ANY = "any"


class CommandEntryPoint(UserFlowEntryPoint):
    """Basic entrypoint catching Telegram /commands"""

    command: str  # without leading slash, e.g. "start" instead of "/start"
    next_block_id: UserFlowBlockId | None
    scope: CommandScope = CommandScope.PRIVATE

    # params for native Telegram menu
    short_description: str | None = None
    menu_rank: int | None = None

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        if self.scope is CommandScope.PRIVATE:
            chat_types: list[tg_const.ChatType] | None = [tg_const.ChatType.private]
        elif self.scope is CommandScope.GROUP:
            chat_types = [tg_const.ChatType.group, tg_const.ChatType.supergroup]
        else:
            chat_types = None

        @context.bot.message_handler(
            commands=[self.command],
            chat_types=chat_types,
            func=context.banned_users_store.not_from_banned_user,
        )
        async def cmd_handler(message: tg.Message) -> None:
            if self.next_block_id is not None:
                await context.enter_block(
                    self.next_block_id,
                    UserFlowContext.from_setup_context(
                        setup_ctx=context,
                        chat=message.chat,
                        user=message.from_user,
                        last_update_content=message,
                    ),
                )

        res = SetupResult.empty()
        if self.short_description is not None:
            if self.scope is CommandScope.PRIVATE:
                scope: tg.BotCommandScope | None = tg.BotCommandScopeAllPrivateChats()
            elif self.scope is CommandScope.GROUP:
                scope = tg.BotCommandScopeAllGroupChats()
            else:
                scope = None
            res.bot_commands.append(
                BotCommandInfo(
                    command=tg.BotCommand(
                        command=self.command,
                        description=self.short_description,
                    ),
                    scope=scope,
                    rank=self.menu_rank,
                )
            )
        return res

    def possible_next_block_ids(self) -> list[str]:
        return without_nones([self.next_block_id])
