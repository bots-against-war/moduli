import enum
from typing import Optional

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


class CommandScope(enum.Enum):
    PRIVATE = enum.auto()
    GROUP = enum.auto()
    ANY = enum.auto()


class CommandEntryPoint(UserFlowEntryPoint):
    """Basic entry-point catching Telegram /commands"""

    command: str  # without leading slash, e.g. "start" instead of "/start"
    next_block_id: Optional[UserFlowBlockId]
    scope: CommandScope = CommandScope.PRIVATE
    short_description: Optional[str] = None  # used for native Telegram menu

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        if self.scope is CommandScope.PRIVATE:
            chat_types: Optional[list[tg_const.ChatType]] = [tg_const.ChatType.private]
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
                scope: Optional[tg.BotCommandScope] = tg.BotCommandScopeAllPrivateChats()
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
                )
            )
        return res
