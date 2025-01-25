import base64
import copy
import time

import pytest
from telebot import types as tg
from telebot.test_util import MockedAsyncTeleBot
from telebot_components.redis_utils.emulation import RedisEmulation
from telebot_components.utils import TextMarkup as ContentTextMarkup

from telebot_constructor.bot_config import (
    BotConfig,
    UserFlowBlockConfig,
    UserFlowConfig,
    UserFlowEntryPointConfig,
)
from telebot_constructor.construct import construct_bot
from telebot_constructor.store.media import Media, RedisMediaStore
from telebot_constructor.user_flow.blocks.content import (
    Content,
    ContentBlock,
    ContentBlockContentAttachment,
    ContentText,
)
from telebot_constructor.user_flow.entrypoints.command import CommandEntryPoint
from tests.utils import (
    assert_method_call_dictified_kwargs_include,
    assert_method_call_kwargs_include,
    dummy_errors_store,
    dummy_form_results_store,
    dummy_secret_store,
    tg_update_message_to_bot,
)


@pytest.mark.parametrize(
    "markdown_text, expected_sent",
    [
        pytest.param(
            "In all other places characters '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', "
            + "'-', '=', '|', '{', '}', '.', '!' must be escaped with the preceding character '\\\\'.",
            (
                r"In all other places characters '\_', '\*', '\[', '\]', '\(', '\)', '\~', '\`', '\>', '\#', '\+', "
                + r"'\-', '\=', '\|', '\{', '\}', '\.', '\!' must be escaped with the preceding character '\\'\."
                + "\n"
            ),
            id="auto escaping stuff for telegram",
        ),
        pytest.param(
            "[link with stuff inside!...](https://google.com)",
            "[link with stuff inside\\!\\.\\.\\.](https://google.com)\n",
            id="escaping inside of links",
        ),
        pytest.param(
            "some text...\n\n>block quote\n>oh it's multiline!\n>    and has a > symbol",
            "some text\\.\\.\\.\n\n>block quote\n>oh it's multiline\\!\n>and has a \\> symbol\n",
            id="block quote",
        ),
    ],
)
async def test_markdown_text(markdown_text: str, expected_sent: str) -> None:
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="testing 1 2",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="command-1",
                        command="start",
                        next_block_id="content-1",
                        short_description="start cmd",
                    ),
                )
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock(
                        block_id="content-1",
                        contents=[
                            Content(
                                text=ContentText(
                                    text=markdown_text,
                                    markup=ContentTextMarkup.MARKDOWN,
                                ),
                                attachments=[],
                            )
                        ],
                        next_block_id=None,
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)

    username = "test"
    await secret_store.save_secret(secret_name="token", secret_value="<token>", owner_id=username)

    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="simple-user-flow-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()

    await bot.process_new_updates([tg_update_message_to_bot(user_id=1234, first_name="User", text="/start")])

    assert len(bot.method_calls) == 1
    sent_text = bot.method_calls["send_message"][0].kwargs["text"]
    assert sent_text == expected_sent
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {
                "text": expected_sent,
                "chat_id": 1234,
                "parse_mode": "MarkdownV2",
            },
        ],
    )
    bot.method_calls.clear()


async def test_single_photo() -> None:
    # setting up dependencies with in-memory redis emulation
    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)

    # creating "secret" with bot token (in prod it is done automatically during bot creation)
    owner_id = "test-username"
    await secret_store.save_secret(secret_name="token", secret_value="<token>", owner_id=owner_id)

    media_store = RedisMediaStore(redis)
    media_id = await media_store.save_media(owner_id, Media(content=b"attachment-body", filename=None))

    # simple bot config with a single /start leading to a single content block
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Content block test bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="command-1",
                        command="start",
                        next_block_id="content-1",
                        short_description="start cmd",
                    ),
                )
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock(
                        block_id="content-1",
                        contents=[
                            Content(
                                text=ContentText(text="photo caption", markup=ContentTextMarkup.HTML),
                                attachments=[ContentBlockContentAttachment(image=media_id)],
                            )
                        ],
                        next_block_id=None,
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    # calling main constructor function, in prod it is done when starting the bot (see /api/start/{bot_id})
    bot_runner = await construct_bot(
        owner_id=owner_id,
        bot_id="simple-user-flow-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        media_store=media_store.adapter_for(owner_id),
        # for tests we use "mocked" bot class instead of the real one; it will not make any requests
        # to Telegram, but store calls so that we can check them as part of the test (see below)
        _bot_factory=MockedAsyncTeleBot,
    )

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)  # just for typing
    # method_calls is a special property existing only on mocked bot class, it stores
    # all calls made on this bot instance; here we clear it, because during setup constructor
    # already made some calls (e.g. getMe) and we're not interested in them in this test
    bot.method_calls.clear()

    # here we imitate user-bot interaction (in prod it would be done when bot receives updates
    # from Telegram, here we do it manually); we have to specify in advance which value bot
    # should receive from Telegram here
    def set_return_for_send_photo():
        bot.add_return_values(
            "send_photo",
            tg.Message(
                message_id=1,
                from_user=tg.User(id=1, is_bot=True, first_name="Bot"),
                date=int(time.time()),
                chat=None,  # type: ignore
                content_type="photo",
                options={
                    "photo": [
                        tg.PhotoSize(
                            file_id="example-file-id",
                            file_unique_id="unused",
                            width=100,
                            height=100,
                        )
                    ]
                },
                json_string={},
            ),
        )

    # first interaction with bot -- it whould send photo as raw bytes, recieve file_id and save it to cache
    set_return_for_send_photo()
    await bot.process_new_updates([tg_update_message_to_bot(user_id=111111, first_name="User", text="/start")])

    # check that the bot responds to this message as expected (sends photo in this case)
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_photo"],
        [
            {
                "caption": "photo caption",
                "photo": b"attachment-body",
                "chat_id": 111111,
                "parse_mode": "HTML",
            },
        ],
    )
    bot.method_calls.clear()

    # second interaction should be the same, but the bot finds a cached file_id for the photo and sends it instead
    # of uploading raw bytes second time
    set_return_for_send_photo()
    await bot.process_new_updates([tg_update_message_to_bot(user_id=111111, first_name="User", text="/start")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_photo"],
        [
            {
                "caption": "photo caption",
                "photo": "example-file-id",
                "chat_id": 111111,
                "parse_mode": "HTML",
            },
        ],
    )
    bot.method_calls.clear()


@pytest.mark.parametrize("media_store_configured", [True, False])
async def test_media_store_error_fallback(media_store_configured: bool) -> None:
    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)

    owner_id = "test-username"
    await secret_store.save_secret(secret_name="token", secret_value="<token>", owner_id=owner_id)

    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Content block test bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="command-1",
                        command="start",
                        next_block_id="content-1",
                        short_description="start cmd",
                    ),
                )
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock(
                        block_id="content-1",
                        contents=[
                            Content(
                                text=ContentText(text="photo caption", markup=ContentTextMarkup.HTML),
                                attachments=[ContentBlockContentAttachment(image="nonexistent")],
                            )
                        ],
                        next_block_id=None,
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    bot_runner = await construct_bot(
        owner_id=owner_id,
        bot_id="simple-user-flow-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        media_store=RedisMediaStore(redis).adapter_for(owner_id) if media_store_configured else None,
        _bot_factory=MockedAsyncTeleBot,
    )

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)  # just for typing
    bot.method_calls.clear()

    await bot.process_new_updates([tg_update_message_to_bot(user_id=111111, first_name="User", text="/start")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {
                "chat_id": 111111,
                "text": "photo caption",
                "parse_mode": "HTML",
            },
        ],
    )
    bot.method_calls.clear()


async def test_multiple_photos() -> None:
    owner_id = "test-username"
    bot_id = "multiple-photos-test-bot"

    redis = RedisEmulation()

    media_store = RedisMediaStore(redis)
    file_1_body = b"file-1-body"
    file_1_media_id = await media_store.save_media(owner_id, Media(content=file_1_body, filename=None))

    secret_store = dummy_secret_store(redis)
    await secret_store.save_secret(secret_name="token", secret_value="<token>", owner_id=owner_id)

    async def make_bot(config: BotConfig) -> MockedAsyncTeleBot:
        bot_runner = await construct_bot(
            owner_id=owner_id,
            bot_id=bot_id,
            bot_config=config,
            form_results_store=dummy_form_results_store(),
            errors_store=dummy_errors_store(),
            secret_store=secret_store,
            redis=redis,
            owner_chat_id=0,
            media_store=media_store.adapter_for(owner_id),
            _bot_factory=MockedAsyncTeleBot,
        )
        bot = bot_runner.bot
        assert isinstance(bot, MockedAsyncTeleBot)
        bot.method_calls.clear()
        return bot

    def set_return_for_send_photo(bot: MockedAsyncTeleBot, file_id: str):
        bot.add_return_values(
            "send_photo",
            tg.Message(
                message_id=1312,
                from_user=tg.User(id=161, is_bot=True, first_name="Bot"),
                date=int(time.time()),
                chat=None,  # type: ignore
                content_type="photo",
                options={
                    "photo": [
                        tg.PhotoSize(
                            file_id=file_id,
                            file_unique_id="unused",
                            width=100,
                            height=100,
                        )
                    ]
                },
                json_string={},
            ),
        )

    bot_config_v1 = BotConfig(
        token_secret_name="token",
        display_name="Content block test bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="command-1",
                        command="start",
                        next_block_id="content-1",
                        short_description="start cmd",
                    ),
                )
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock(
                        block_id="content-1",
                        contents=[
                            Content(
                                text=ContentText(text="photo album for u", markup=ContentTextMarkup.HTML),
                                attachments=[
                                    ContentBlockContentAttachment(image=file_1_media_id),
                                ],
                            )
                        ],
                        next_block_id=None,
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )
    bot = await make_bot(bot_config_v1)
    set_return_for_send_photo(bot, "file-1-id")
    await bot.process_new_updates([tg_update_message_to_bot(user_id=1900, first_name="User", text="/start")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_photo"],
        [{"chat_id": 1900, "photo": b"file-1-body", "caption": "photo album for u", "parse_mode": "HTML"}],
    )
    bot.method_calls.clear()

    # attachment with invalid media id is simply ignored, the first file id is cached
    bot_config_v2 = copy.deepcopy(bot_config_v1)
    bot_config_v2.user_flow_config.blocks[0].content.contents[0].attachments.append(  # type: ignore
        ContentBlockContentAttachment(image="non-existent-media-id"),
    )
    bot = await make_bot(bot_config_v2)
    set_return_for_send_photo(bot, "file-1-id")
    await bot.process_new_updates([tg_update_message_to_bot(user_id=1900, first_name="User", text="/start")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_photo"],
        [{"chat_id": 1900, "photo": "file-1-id", "caption": "photo album for u", "parse_mode": "HTML"}],
    )
    bot.method_calls.clear()

    def set_return_for_send_media_group(bot: MockedAsyncTeleBot, response_file_ids: list[str]):
        bot.add_return_values(
            "send_media_group",
            [
                tg.Message(
                    message_id=1312,
                    from_user=tg.User(id=161, is_bot=True, first_name="Bot"),
                    date=int(time.time()),
                    chat=None,  # type: ignore
                    content_type="photo",
                    options={
                        "photo": [
                            tg.PhotoSize(
                                file_id=file_id,
                                file_unique_id="unused",
                                width=100,
                                height=100,
                            )
                        ]
                    },
                    json_string={},
                )
                for file_id in response_file_ids
            ],
        )

    # adding a second new attachment, the first should still be cached
    file_2_body = b"file-2-body"
    file_2_media_id = await media_store.save_media(owner_id, Media(content=file_2_body, filename=None))
    bot_config_v3 = copy.deepcopy(bot_config_v1)
    bot_config_v3.user_flow_config.blocks[0].content.contents[0].attachments.append(  # type: ignore
        ContentBlockContentAttachment(image=file_2_media_id),
    )
    bot = await make_bot(bot_config_v3)
    set_return_for_send_media_group(bot, ["file-id-1", "file-id-2"])
    await bot.process_new_updates([tg_update_message_to_bot(user_id=1900, first_name="User", text="/start")])
    assert len(bot.method_calls) == 1
    assert len(bot.method_calls["send_media_group"]) == 1
    smg_kwargs = bot.method_calls["send_media_group"][0].full_kwargs
    assert smg_kwargs["chat_id"] == 1900
    m1_dict = smg_kwargs["media"][0].to_dict()
    assert m1_dict == {"type": "photo", "media": "file-1-id", "caption": "photo album for u", "parse_mode": "HTML"}
    assert smg_kwargs["media"][1].media == b"file-2-body"
    bot.method_calls.clear()

    # now both cached
    set_return_for_send_media_group(bot, ["file-id-1", "file-id-2"])
    await bot.process_new_updates([tg_update_message_to_bot(user_id=1900, first_name="User", text="/start")])
    assert len(bot.method_calls) == 1
    assert len(bot.method_calls["send_media_group"]) == 1
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["send_media_group"],
        [
            {
                "chat_id": 1900,
                "media": [
                    {
                        "media_json": (
                            '{"type":"photo","media":"file-1-id",'
                            + '"caption":"photo album for u","parse_mode":"HTML"}'
                        ),
                        "files": None,
                    },
                    {"media_json": '{"type":"photo","media":"file-id-2"}', "files": None},
                ],
            }
        ],
    )
    bot.method_calls.clear()


def test_content_block_separates_too_long_caption() -> None:
    block = ContentBlock(
        block_id="content",
        contents=[
            Content(
                text=ContentText(
                    text="this caption is too long " * 100,
                    markup=ContentTextMarkup.HTML,
                ),
                attachments=[
                    ContentBlockContentAttachment(image=base64.b64encode(b"stuff").decode()),
                ],
            )
        ],
        next_block_id=None,
    )

    assert len(block.contents) == 2
    text_content = block.contents[0]
    assert not text_content.attachments
    assert text_content.text is not None
    assert text_content.text.text == "this caption is too long " * 100
    img_content = block.contents[1]
    assert img_content.text is None
    assert len(img_content.attachments) == 1


def test_content_block_splits_too_many_attachments() -> None:
    block = ContentBlock(
        block_id="content",
        contents=[
            Content(
                text=ContentText(
                    text="this caption is too long " * 100,
                    markup=ContentTextMarkup.HTML,
                ),
                attachments=[ContentBlockContentAttachment(image=f"stuff-{idx}") for idx in range(15)],
            )
        ],
        next_block_id=None,
    )

    assert len(block.contents) == 3
    text_content = block.contents[0]
    assert not text_content.attachments
    assert text_content.text is not None
    assert text_content.text.text == "this caption is too long " * 100

    img_content_1 = block.contents[1]
    assert img_content_1.text is None
    assert len(img_content_1.attachments) == 10

    img_content_2 = block.contents[2]
    assert img_content_2.text is None
    assert len(img_content_2.attachments) == 5
