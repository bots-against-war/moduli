import collections
import dataclasses
import datetime
import logging
from dataclasses import dataclass
from typing import List, Optional

from telebot import AsyncTeleBot
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.banned_users import BannedUsersStore
from telebot_components.stores.generic import KeyValueStore

from telebot_constructor.store.errors import BotSpecificErrorsStore
from telebot_constructor.store.form_results import BotSpecificFormResultsStore
from telebot_constructor.store.media import UserSpecificMediaStore
from telebot_constructor.store.menu import MenuMetadataStore
from telebot_constructor.user_flow.blocks.base import UserFlowBlock
from telebot_constructor.user_flow.blocks.form import FormBlock
from telebot_constructor.user_flow.blocks.human_operator import HumanOperatorBlock
from telebot_constructor.user_flow.blocks.language_select import LanguageSelectBlock
from telebot_constructor.user_flow.entrypoints.base import UserFlowEntryPoint
from telebot_constructor.user_flow.entrypoints.command import CommandEntryPoint
from telebot_constructor.user_flow.types import (
    SetupResult,
    UserFlowBlockId,
    UserFlowContext,
    UserFlowSetupContext,
)
from telebot_constructor.utils import validate_unique

logger = logging.getLogger(__name__)


@dataclass
class UserFlow:
    entrypoints: List[UserFlowEntryPoint]
    blocks: List[UserFlowBlock]

    def __post_init__(self) -> None:
        self._active_block_id_store: Optional[KeyValueStore[str]] = None

        validate_unique([b.block_id for b in self.blocks], items_name="block ids")
        validate_unique([e.entrypoint_id for e in self.entrypoints], items_name="entrypoint ids")
        self.block_by_id = {block.block_id: block for block in self.blocks}

        self.nodes_leading_to: dict[str, list[str]] = collections.defaultdict(list)
        for node in self.blocks + self.entrypoints:
            for next_block_id in node.possible_next_block_ids():
                if next_block_id not in self.block_by_id:
                    raise ValueError(
                        f"Block/entrypoing {node} references a non-existent block "
                        + f"as a possible next block: {next_block_id}"
                    )
                self.nodes_leading_to[next_block_id].append(
                    node.block_id if isinstance(node, UserFlowBlock) else node.entrypoint_id
                )

        catch_all_nodes = [entrypoint for entrypoint in self.entrypoints if entrypoint.is_catch_all()] + [
            block for block in self.blocks if block.is_catch_all()
        ]
        if len(catch_all_nodes) > 1:
            raise ValueError(
                "At most one catch-all block/entrypoint is allowed, but found: "
                + f"{', '.join(str(e) for e in catch_all_nodes)}"
            )

        validate_unique(
            [entrypoint.command for entrypoint in self.entrypoints if isinstance(entrypoint, CommandEntryPoint)],
            items_name="commands",
        )

        language_select_blocks = [block for block in self.blocks if isinstance(block, LanguageSelectBlock)]
        if len(language_select_blocks) > 1:
            raise ValueError(
                f"At most one language selection block is allowed in the user flow, found {len(language_select_blocks)}"
            )
        self.language_select_block = language_select_blocks[0] if language_select_blocks else None

        self.human_operator_blocks = [block for block in self.blocks if isinstance(block, HumanOperatorBlock)]
        validate_unique(
            [b.feedback_handler_config.admin_chat_id for b in self.human_operator_blocks],
            items_name="admin chat ids in human operator blocks",
        )

        validate_unique([b.form_name for b in self.blocks if isinstance(b, FormBlock)], items_name="form names")

    @property
    def active_block_id_store(self) -> KeyValueStore[str]:
        if self._active_block_id_store is None:
            raise RuntimeError("Active block id is not properly initialized, probably accessed before setup")
        return self._active_block_id_store

    async def _enter_block(self, id: UserFlowBlockId, context: UserFlowContext) -> None:
        # prevent infinite loops in a single interaction (e.g. message block leads to itself
        # and repeats indefinitely); in general, loops are allowed if they require user interaction
        # to proceed (e.g. two menu blocks leading to each other)
        if id in context.visited_block_ids:
            raise RuntimeError(f"Likely loop in user flow, attempted to enter the block twice: {id}")
        context.visited_block_ids.add(id)
        if await context.banned_users_store.is_banned(context.user.id):
            return
        block = self.block_by_id.get(id)
        if block is None:
            raise ValueError(f"Attempt to enter non-existent block with id {id}")
        await self.active_block_id_store.save(context.user.id, block.block_id)
        await block.enter(context)

    async def _get_active_block_id(self, user_id: int) -> Optional[UserFlowBlockId]:
        return await self.active_block_id_store.load(user_id)

    async def setup(
        self,
        bot_prefix: str,
        bot: AsyncTeleBot,
        redis: RedisInterface,
        banned_users_store: BannedUsersStore,
        form_results_store: BotSpecificFormResultsStore,
        errors_store: BotSpecificErrorsStore,
        media_store: UserSpecificMediaStore | None,
        owner_chat_id: int,
    ) -> SetupResult:
        self._active_block_id_store = KeyValueStore[str](
            name="user-flow-active-block",
            prefix=bot_prefix,
            redis=redis,
            expiration_time=datetime.timedelta(days=14),
            dumper=str,
            loader=str,
        )

        # setting up flow elements
        setup_result = SetupResult.empty()
        setup_context = UserFlowSetupContext(
            bot_prefix=bot_prefix,
            bot=bot,
            redis=redis,
            form_results_store=form_results_store,
            errors_store=errors_store,
            banned_users_store=banned_users_store,
            media_store=media_store,
            menu_metadata_store=MenuMetadataStore(redis, bot_prefix),
            feedback_handlers=dict(),
            language_store=None,  # set later, when landuage select blocks are set up
            enter_block=self._enter_block,
            get_active_block_id=self._get_active_block_id,
            owner_chat_id=owner_chat_id,
        )
        setup_block_ids: set[str] = set()

        if self.language_select_block is not None:
            logger.info(f"[{bot_prefix}] Setting up language selection block first")
            setup_result.merge(await self.language_select_block.setup(context=setup_context))
            # adding language store to the context for other blocks to use (validate their texts
            # as multilang and pass it to components)
            setup_context = dataclasses.replace(setup_context, language_store=self.language_select_block.language_store)
            setup_block_ids.add(self.language_select_block.block_id)

        logger.info(f"[{bot_prefix}] Setting up human operator blocks (total of {len(self.human_operator_blocks)})")
        for ho_block in self.human_operator_blocks:
            setup_block_ids.add(ho_block.block_id)
            setup_result.merge(await ho_block.setup(context=setup_context))
            # saving feedback handler to global context for other blocks to use
            setup_context.feedback_handlers[ho_block.feedback_handler_config.admin_chat_id] = ho_block.feedback_handler
            setup_block_ids.add(ho_block.block_id)

        for idx, entrypoint in enumerate(self.entrypoints):
            logger.info(f"[{bot_prefix}] Setting up entrypoint {idx + 1} / {len(self.entrypoints)}: {entrypoint}")
            try:
                entrypoint_setup_result = await entrypoint.setup(setup_context)
            except Exception as e:
                raise ValueError(f"Error setting up {entrypoint}: {e}") from e
            setup_result.merge(entrypoint_setup_result)

        for idx, block in enumerate(self.blocks):
            if block.block_id in setup_block_ids:
                continue
            logger.info(f"[{bot_prefix}] Setting up block {idx + 1} / {len(self.blocks)}: {block}")
            try:
                block_setup_result = await block.setup(setup_context)
            except Exception as e:
                raise ValueError(f"Error setting up {block}: {e}") from e
            setup_result.merge(block_setup_result)

        return setup_result
