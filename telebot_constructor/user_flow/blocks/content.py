import datetime
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel
from telebot import types as tg
from telebot_components.language import any_text_to_str, vaildate_singlelang_text
from telebot_components.stores.generic import KeyValueStore
from telebot_components.utils import TextMarkup

from telebot_constructor.store.media import Media
from telebot_constructor.user_flow.blocks.base import UserFlowBlock
from telebot_constructor.user_flow.types import (
    SetupResult,
    UserFlowBlockId,
    UserFlowContext,
    UserFlowSetupContext,
)
from telebot_constructor.utils import (
    iter_batches,
    preprocess_for_telegram,
    without_nones,
)
from telebot_constructor.utils.pydantic import (
    ExactlyOneNonNullFieldModel,
    LocalizableText,
)


class ContentText(BaseModel):
    text: LocalizableText
    markup: TextMarkup

    _preprocessed_text: LocalizableText | None = None

    @property
    def preprocessed(self) -> LocalizableText:
        return self._preprocessed_text or self.text

    def model_post_init(self, __context: Any) -> None:
        self._preprocessed_text = preprocess_for_telegram(self.text, self.markup)

    def is_empty(self) -> bool:
        if isinstance(self.text, str):
            return len(self.text) == 0
        else:
            return any(len(v) == 0 for v in self.text.values())


DATA_URL_PREFIX_REGEX = re.compile(r"^data:\w+/\w+;base64,")


class ContentBlockContentAttachment(ExactlyOneNonNullFieldModel):
    image: Optional[str]  # media id in media store

    def media_id(self) -> str:
        # runtime guarantee that at least one (now it's always image) option is non-None
        return self.image  # type: ignore

    def is_legacy_base64_image(self) -> bool:
        return self.image is not None and (
            DATA_URL_PREFIX_REGEX.match(self.image) is not None
            or len(self.image) > 1024  # 1024 - sensible limit for media_id, otherwise it's likely b64
        )


class Content(BaseModel):
    text: Optional[ContentText]
    attachments: list[ContentBlockContentAttachment]

    def model_post_init(self, __context: Any) -> None:
        self.attachments = [a for a in self.attachments if not a.is_legacy_base64_image()]


class ContentBlock(UserFlowBlock):
    """
    Simplest user flow block: static content sent by bot in one or several telegram messages.
    Immediately continues to the next block after sending the content.
    """

    contents: list[Content]
    next_block_id: Optional[UserFlowBlockId]

    def possible_next_block_ids(self) -> list[str]:
        return without_nones([self.next_block_id])

    def model_post_init(self, __context: Any) -> None:
        self._logger = logging.getLogger(__name__)

        if not self.contents:
            raise ValueError("Block must contain at least one content unit")
        empty_contents = [c for c in self.contents if (c.text is None or c.text.is_empty()) and not c.attachments]
        if empty_contents:
            raise ValueError(f"Block contains empty content unit(s): {len(empty_contents)}")
        contents_validated: list[Content] = []
        for c in self.contents:
            # checking for too long captions (too long texts are split automatically by telebot library)
            # limit is 1024 symbols, see docs: https://core.telegram.org/bots/api#inputmediaphoto
            # note that we are here conservative as we includes e.g. HTML markup in the symbol bugdet
            if c.attachments and c.text is not None and len(c.text.preprocessed) > 1024:
                # splitting long text and attachments into separate units
                contents_validated.append(Content(text=c.text, attachments=[]))
                c = Content(text=None, attachments=c.attachments)

            # checking for too many attachments
            if len(c.attachments) > 10:
                batches = list(iter_batches(c.attachments, size=10))
                contents_validated.append(Content(text=c.text, attachments=batches[0]))
                contents_validated.extend(Content(text=None, attachments=batch) for batch in batches[1:-1])
                c = Content(text=None, attachments=batches[-1])

            # when we support multiple attachment types, we should also check attachment compatibility
            # (e.g. photo + audio is disallowed)

            contents_validated.append(c)

        self.contents = contents_validated

    @classmethod
    def simple_text(
        cls, block_id: str, message_text: LocalizableText, next_block_id: Optional[UserFlowBlockId]
    ) -> "ContentBlock":
        """For use in tests"""
        return ContentBlock(
            block_id=block_id,
            contents=[
                Content(
                    text=ContentText(
                        text=message_text,
                        markup=TextMarkup.NONE,
                    ),
                    attachments=[],
                )
            ],
            next_block_id=next_block_id,
        )

    async def enter(self, context: UserFlowContext) -> None:
        chat_id = context.chat.id if context.chat is not None else context.user.id
        language = (
            await self._language_store.get_user_language(context.user) if self._language_store is not None else None
        )
        for content in self.contents:
            parse_mode = content.text.markup.parse_mode() if content.text is not None else None

            # preparing attachments: either loading from cache or from storage
            prepared_attachments: list[PreparedAttachment] = []
            for attachment in content.attachments:
                source: str | Media | None = await self._tg_file_id_by_media_id_store.load(attachment.media_id())
                if source is None and self._media_store is not None:
                    source = await self._media_store.load_media(attachment.media_id())
                    if source is None:
                        self._logger.error(
                            f"Failed to load media from the store: {attachment.media_id()}; will proceed without it"
                        )
                if source is not None:
                    prepared_attachments.append(
                        PreparedAttachment(
                            attachment=attachment,
                            source=source,
                        )
                    )
            self._logger.debug("Prepared attachments: %s", prepared_attachments)

            if not prepared_attachments:
                if content.text is not None:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=any_text_to_str(content.text.preprocessed, language),
                        parse_mode=parse_mode,
                        reply_markup=tg.ReplyKeyboardRemove(),
                    )
                else:
                    self._logger.error("Empty content block: no text and no attachments!")
            else:
                # sending attachments and caching resulting file ids
                if len(prepared_attachments) == 1:
                    # single attachment
                    pa = prepared_attachments[0]
                    if pa.attachment.image is not None:
                        messages = [
                            await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=pa.telegram_attachment(),
                                caption=(
                                    any_text_to_str(content.text.preprocessed, language)
                                    if content.text is not None
                                    else None
                                ),
                                parse_mode=parse_mode if content.text is not None else None,
                                reply_markup=tg.ReplyKeyboardRemove(),
                            )
                        ]
                    else:
                        self._logger.error("Unexpected attachment type; only images are supported for now")
                        messages = []
                else:
                    # multiple attachments case
                    tg_input_media = [
                        # input media handles both file_id and raw bytes case, even though it's not properly typed
                        tg.InputMediaPhoto(pa.telegram_attachment())  # type: ignore
                        for pa in prepared_attachments
                    ]
                    # for media groups, text content is put to first media's caption
                    if content.text is not None:
                        tg_input_media[0].caption = any_text_to_str(content.text.preprocessed, language)
                        tg_input_media[0].parse_mode = parse_mode
                        # NOTE: reply markup is not available for media groups, so we don't send it

                    messages = await context.bot.send_media_group(
                        chat_id=chat_id,
                        # bad typing in telebot (list[InputMediaPhoto | ...], complains because list is invariant)
                        media=list(tg_input_media),
                    )

                self._logger.debug(f"Sent attachments in messages: {messages}")

                if len(messages) != len(prepared_attachments):
                    self._logger.error(
                        "The number of messages doesn't match the number of attachments"
                        + f"({len(messages) = }, {len(prepared_attachments) = })"
                    )

                for message, pa in zip(messages, prepared_attachments):
                    if isinstance(pa.source, str):
                        # already cached
                        continue
                    if message.photo is None:
                        self._logger.error("Got Message object without photo on unable to fill the cache, ignoring it")
                        continue
                    new_file_id = message.photo[0].file_id
                    self._logger.debug(f"Caching Telegram file_id for attachment: {pa} -> {new_file_id}")
                    await self._tg_file_id_by_media_id_store.save(pa.attachment.media_id(), new_file_id)

        if self.next_block_id is not None:
            await context.enter_block(self.next_block_id, context)

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        self._logger = context.make_instrumented_logger(__name__, self.block_id)
        self._tg_file_id_by_media_id_store = KeyValueStore[str](
            name="file-id",
            prefix=context.bot_prefix,
            redis=context.redis,
            expiration_time=datetime.timedelta(days=180),
            dumper=str,
            loader=str,
        )

        self._language_store = context.language_store
        # validating texts against language store
        for c in self.contents:
            if c.text is None:
                continue
            if self._language_store is not None:
                self._language_store.validate_multilang(c.text.preprocessed)
            else:
                vaildate_singlelang_text(c.text.preprocessed)

        self._media_store = context.media_store

        return SetupResult.empty()


def md5_hash(data: str) -> str:
    return hashlib.md5(data.encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass
class PreparedAttachment:
    """Helper class to store information about where do we source the given attachment from"""

    attachment: ContentBlockContentAttachment
    source: str | Media  # str = Telegram file id, Media = new raw media

    def telegram_attachment(self) -> str | bytes:
        if isinstance(self.source, str):
            return self.source  # file_id
        else:
            return self.source.content
