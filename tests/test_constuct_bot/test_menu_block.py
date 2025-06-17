from telebot.test_util import MockedAsyncTeleBot
from telebot_components.redis_utils.emulation import RedisEmulation

from telebot_constructor.bot_config import (
    BotConfig,
    UserFlowBlockConfig,
    UserFlowConfig,
    UserFlowEntryPointConfig,
)
from telebot_constructor.construct import construct_bot
from telebot_constructor.user_flow.blocks.content import ContentBlock
from telebot_constructor.user_flow.blocks.menu import (
    Menu,
    MenuBlock,
    MenuConfig,
    MenuItem,
    MenuMechanism,
)
from telebot_constructor.user_flow.entrypoints.command import CommandEntryPoint
from tests.utils import (
    assert_method_call_dictified_kwargs_include,
    assert_method_call_kwargs_include,
    dummy_errors_store,
    dummy_form_results_store,
    dummy_secret_store,
    tg_update_callback_query,
    tg_update_message_to_bot,
)


async def test_flow_with_menu() -> None:
    USER_ID = 1312
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Menu bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="command-1",
                        command="start",
                        next_block_id="start-message",
                    ),
                )
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="start-message",
                        message_text="start message",
                        next_block_id="menu",
                    ),
                ),
                UserFlowBlockConfig(
                    menu=MenuBlock(
                        block_id="menu",
                        menu=Menu(
                            text="top level menu",
                            items=[
                                MenuItem(label="one", next_block_id="message-1"),
                                MenuItem(label="two", next_block_id="message-2"),
                            ],
                            config=MenuConfig(
                                back_label="<-",
                                lock_after_termination=False,
                                mechanism=MenuMechanism.INLINE_BUTTONS,
                            ),
                        ),
                    )
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-1",
                        message_text="message on option one",
                        next_block_id=None,
                    ),
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-2",
                        message_text="message on option two",
                        next_block_id=None,
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "user123"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="menu-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )

    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()  # remove construct-time calls

    # /start command
    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="/start")])
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {"chat_id": USER_ID, "text": "start message"},
            {"chat_id": USER_ID, "text": "top level menu"},
        ],
    )
    assert bot.method_calls["send_message"][1].full_kwargs["reply_markup"].to_dict() == {
        "inline_keyboard": [
            [{"text": "one", "callback_data": "action:a296a4e2c3d1da31f09426194a558038"}],
            [{"text": "two", "callback_data": "action:30c04eafbba0c73a79ee472f53ae67d9"}],
        ]
    }
    bot.method_calls.clear()

    # pressing the first button
    await bot.process_new_updates(
        [tg_update_callback_query(USER_ID, first_name="User", callback_query="action:a296a4e2c3d1da31f09426194a558038")]
    )
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"], [{"chat_id": 1312, "text": "message on option one"}]
    )
    assert bot.method_calls["send_message"][0].full_kwargs["reply_markup"].to_json() == '{"remove_keyboard":true}'
    bot.method_calls.clear()

    # pressing the second button
    await bot.process_new_updates(
        [tg_update_callback_query(USER_ID, first_name="User", callback_query="action:30c04eafbba0c73a79ee472f53ae67d9")]
    )
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"], [{"chat_id": 1312, "text": "message on option two"}]
    )
    assert bot.method_calls["send_message"][0].full_kwargs["reply_markup"].to_json() == '{"remove_keyboard":true}'
    bot.method_calls.clear()


async def test_flow_with_multilevel_menu() -> None:
    USER_ID = 1312
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Menu bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="start-cmd",
                        command="start",
                        next_block_id="menu",
                    ),
                )
            ],
            blocks=[
                UserFlowBlockConfig(
                    menu=MenuBlock(
                        block_id="menu",
                        menu=Menu(
                            text="top level menu",
                            items=[
                                MenuItem(label="one", next_block_id="submenu"),
                                MenuItem(label="two", next_block_id="message-fin"),
                            ],
                            config=MenuConfig(
                                back_label="<-",
                                lock_after_termination=False,
                                mechanism=MenuMechanism.INLINE_BUTTONS,
                            ),
                        ),
                    )
                ),
                UserFlowBlockConfig(
                    menu=MenuBlock(
                        block_id="submenu",
                        menu=Menu(
                            text="second level menu",
                            items=[
                                MenuItem(label="foo", next_block_id="message-fin"),
                                MenuItem(label="bar", next_block_id="message-fin"),
                            ],
                            config=MenuConfig(
                                back_label="<-",
                                lock_after_termination=False,
                                mechanism=MenuMechanism.INLINE_BUTTONS,
                            ),
                        ),
                    )
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-fin",
                        message_text="message after menu",
                        next_block_id=None,
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "user12345"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="menu-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )

    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()

    # /start command
    user_msg_id = 1
    await bot.process_new_updates(
        [tg_update_message_to_bot(USER_ID, first_name="User", text="/start", message_id=user_msg_id)]
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["send_message"],
        [
            {
                "chat_id": USER_ID,
                "text": "top level menu",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "one", "callback_data": "action:5d9b64fb776b71bb217dbd48e1a3e6a5"}],
                        [{"text": "two", "callback_data": "action:7f2eb610665b88cd72dba67770b674b4"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    menu_msg_id = bot._latest_message_id_by_chat[USER_ID]

    # pressing the second (terminating) button
    await bot.process_new_updates(
        [
            tg_update_callback_query(
                USER_ID,
                first_name="User",
                callback_query="action:7f2eb610665b88cd72dba67770b674b4",
                message_id=menu_msg_id,
            )
        ]
    )
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"], [{"chat_id": 1312, "text": "message after menu"}]
    )
    assert bot.method_calls["send_message"][0].full_kwargs["reply_markup"].to_json() == '{"remove_keyboard":true}'
    bot.method_calls.clear()

    # now pressing the first button
    await bot.process_new_updates(
        [
            tg_update_callback_query(
                USER_ID,
                first_name="User",
                callback_query="action:5d9b64fb776b71bb217dbd48e1a3e6a5",
                message_id=menu_msg_id,
            )
        ]
    )
    assert not bot.method_calls.get("send_message")
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": 1312,
                "text": "second level menu",
                "message_id": 2,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "foo", "callback_data": "action:6a5939a15a2a05265a71e9828ca655c6"}],
                        [{"text": "bar", "callback_data": "action:6a5939a15a2a05265a71e9828ca655c6"}],
                        [{"text": "<-", "callback_data": "action:eecfc468ceb0c62dce4e91522a7a4bbe"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    # pressing the first button in submeny
    await bot.process_new_updates(
        [
            tg_update_callback_query(
                USER_ID,
                first_name="User",
                callback_query="action:6a5939a15a2a05265a71e9828ca655c6",
                message_id=menu_msg_id,
            )
        ]
    )
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"], [{"chat_id": 1312, "text": "message after menu"}]
    )
    bot.method_calls.clear()

    # going back to the top-level
    await bot.process_new_updates(
        [
            tg_update_callback_query(
                USER_ID,
                first_name="User",
                callback_query="action:eecfc468ceb0c62dce4e91522a7a4bbe",
                message_id=menu_msg_id,
            )
        ]
    )
    assert not bot.method_calls.get("send_message")
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": 1312,
                "text": "top level menu",
                "message_id": 2,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "one", "callback_data": "action:5d9b64fb776b71bb217dbd48e1a3e6a5"}],
                        [{"text": "two", "callback_data": "action:7f2eb610665b88cd72dba67770b674b4"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()


def make_menu_blocks(connections: dict[str, list[str]]) -> list[MenuBlock]:
    return [
        MenuBlock(
            block_id=f"menu-{menu_name}",
            menu=Menu(
                text=menu_name,
                items=[
                    MenuItem(
                        label=submenu_name,
                        next_block_id=f"menu-{submenu_name}",
                    )
                    for submenu_name in next_block_ids
                ],
                config=MenuConfig(
                    back_label="<-",
                    lock_after_termination=False,
                    mechanism=MenuMechanism.INLINE_BUTTONS,
                ),
            ),
        )
        for menu_name, next_block_ids in connections.items()
    ]


async def test_multilevel_menu() -> None:
    """
    A multilevel menu that is traversible back and forth
    ┌───┐
    │ A │
    └─┬─┘
      │
    ┌─▼─┐
    │ B │
    └─┬─┘
      │
    ┌─▼─┐
    │ C │
    └───┘
    """
    USER_ID = 1312

    menu_a, menu_b, menu_c = make_menu_blocks({"A": ["B"], "B": ["C"], "C": []})
    menu_c.menu.items.append(MenuItem(label="finish", next_block_id="fin-message"))
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Menu bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(entrypoint_id="start-cmd", command="start", next_block_id="menu-A"),
                )
            ],
            blocks=[
                UserFlowBlockConfig(menu=menu_a),
                UserFlowBlockConfig(menu=menu_b),
                UserFlowBlockConfig(menu=menu_c),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(block_id="fin-message", message_text="finish", next_block_id=None),
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "user12345"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="menu-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )

    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()

    # /start command
    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="/start")])
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["send_message"],
        [
            {
                "chat_id": USER_ID,
                "text": "A",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "B", "callback_data": "action:1b63f1a5c540280108c3f772a54e7e7a"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    menu_msg_id = bot._latest_message_id_by_chat[USER_ID]

    # to the next menu
    await bot.process_new_updates(
        [
            tg_update_callback_query(
                USER_ID,
                first_name="User",
                callback_query="action:1b63f1a5c540280108c3f772a54e7e7a",
                message_id=menu_msg_id,
            )
        ]
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "message_id": menu_msg_id,
                "chat_id": 1312,
                "text": "B",
                "parse_mode": None,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "C", "callback_data": "action:ae64272b007932d17220d5e5d9870452"}],
                        [{"text": "<-", "callback_data": "action:3b4faf3c174efaba47f16a4dce424597"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    # ...and to the next
    await bot.process_new_updates(
        [
            tg_update_callback_query(
                USER_ID,
                first_name="User",
                callback_query="action:ae64272b007932d17220d5e5d9870452",
                message_id=menu_msg_id,
            )
        ]
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": 1312,
                "text": "C",
                "message_id": menu_msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "finish", "callback_data": "action:a59095b0b9144fd6dfc66faac7695e48"}],
                        [{"text": "<-", "callback_data": "action:d8f99604d411721de13accee9ca0d745"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    # back to B
    await bot.process_new_updates(
        [
            tg_update_callback_query(
                USER_ID,
                first_name="User",
                callback_query="action:d8f99604d411721de13accee9ca0d745",
                message_id=menu_msg_id,
            )
        ]
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": 1312,
                "text": "B",
                "parse_mode": None,
                "message_id": menu_msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "C", "callback_data": "action:ae64272b007932d17220d5e5d9870452"}],
                        [{"text": "<-", "callback_data": "action:3b4faf3c174efaba47f16a4dce424597"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()


async def test_dag_menu() -> None:
    """
    A menu with a DAG connection.

    The menu has two entry points: from A, in which case the "back" from E will lead to D because
    it's a shorter path from root; from B, in which case only B-C-E branch is accessible as a
    linear 2-level menu

        ┌───┐
      ┌─┤ A ├─┐
      │ └───┘ │
    ┌─▼─┐   ┌─▼─┐
    │ B │   │ D │
    └─┬─┘   └─┬─┘
    ┌─▼─┐   ┌─▼─┐
    │ C │──►│ E │
    └───┘   └───┘
    """
    USER_ID = 1312

    menu_blocks = make_menu_blocks({"A": ["B", "D"], "B": ["C"], "C": ["E"], "D": ["E"], "E": []})
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Menu bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(entrypoint_id="start-cmd", command="start", next_block_id="menu-A"),
                ),
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(entrypoint_id="aux-cmd", command="aux", next_block_id="menu-B"),
                ),
            ],
            blocks=[UserFlowBlockConfig(menu=menu) for menu in menu_blocks],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "user12345"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="menu-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )

    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()

    # entry point 1

    # /start command
    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="/start")])
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["send_message"],
        [
            {
                "chat_id": USER_ID,
                "text": "A",
                "parse_mode": None,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "B", "callback_data": "action:1b63f1a5c540280108c3f772a54e7e7a"}],
                        [{"text": "D", "callback_data": "action:8bd0a2d362f0ef5713fc72ccb87b798b"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    msg_id = bot._latest_message_id_by_chat[USER_ID]
    kwargs = dict(user_id=USER_ID, first_name="User", message_id=msg_id)

    # D -> E branch
    await bot.process_new_updates(
        [tg_update_callback_query(callback_query="action:8bd0a2d362f0ef5713fc72ccb87b798b", **kwargs)]  # type: ignore
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": USER_ID,
                "text": "D",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "E", "callback_data": "action:53a5b1e69b16fda19d316b84e1668798"}],
                        [{"text": "<-", "callback_data": "action:6b5552ba8e186bd4152303f6b612adbb"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    await bot.process_new_updates(
        [tg_update_callback_query(callback_query="action:53a5b1e69b16fda19d316b84e1668798", **kwargs)]  # type: ignore
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": USER_ID,
                "text": "E",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [[{"text": "<-", "callback_data": "action:45e098856e1190fbd9aae06876a57ae9"}]]
                },
            }
        ],
    )
    bot.method_calls.clear()

    # going back to the main menu
    await bot.process_new_updates(
        [
            tg_update_callback_query(callback_query="action:45e098856e1190fbd9aae06876a57ae9", **kwargs),  # type: ignore
            tg_update_callback_query(callback_query="action:6b5552ba8e186bd4152303f6b612adbb", **kwargs),  # type: ignore
        ],
    )
    bot.method_calls.clear()

    # B -> C branch
    await bot.process_new_updates(
        [tg_update_callback_query(callback_query="action:1b63f1a5c540280108c3f772a54e7e7a", **kwargs)]  # type: ignore
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": USER_ID,
                "text": "B",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "C", "callback_data": "action:ae64272b007932d17220d5e5d9870452"}],
                        [{"text": "<-", "callback_data": "action:3b4faf3c174efaba47f16a4dce424597"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    await bot.process_new_updates(
        [tg_update_callback_query(callback_query="action:ae64272b007932d17220d5e5d9870452", **kwargs)]  # type: ignore
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": USER_ID,
                "text": "C",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "E", "callback_data": "action:662f086213b5979b74ad0cd1e4c60416"}],
                        [{"text": "<-", "callback_data": "action:d8f99604d411721de13accee9ca0d745"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    await bot.process_new_updates(
        [tg_update_callback_query(callback_query="action:662f086213b5979b74ad0cd1e4c60416", **kwargs)]  # type: ignore
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": USER_ID,
                "text": "E",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [[{"text": "<-", "callback_data": "action:45e098856e1190fbd9aae06876a57ae9"}]]
                },
            }
        ],
    )
    bot.method_calls.clear()

    await bot.process_new_updates(
        [
            tg_update_callback_query(callback_query="action:45e098856e1190fbd9aae06876a57ae9", **kwargs),  # type: ignore
            tg_update_callback_query(callback_query="action:d8f99604d411721de13accee9ca0d745", **kwargs),  # type: ignore
            tg_update_callback_query(callback_query="action:3b4faf3c174efaba47f16a4dce424597", **kwargs),  # type: ignore
        ]
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": USER_ID,
                "text": "C",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "E", "callback_data": "action:662f086213b5979b74ad0cd1e4c60416"}],
                        [{"text": "<-", "callback_data": "action:d8f99604d411721de13accee9ca0d745"}],
                    ]
                },
            },
            {
                "chat_id": USER_ID,
                "text": "B",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "C", "callback_data": "action:ae64272b007932d17220d5e5d9870452"}],
                        [{"text": "<-", "callback_data": "action:3b4faf3c174efaba47f16a4dce424597"}],
                    ]
                },
            },
            {
                "chat_id": USER_ID,
                "text": "A",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "B", "callback_data": "action:1b63f1a5c540280108c3f772a54e7e7a"}],
                        [{"text": "D", "callback_data": "action:8bd0a2d362f0ef5713fc72ccb87b798b"}],
                    ]
                },
            },
        ],
    )
    bot.method_calls.clear()

    # entry point 2

    # /aux command
    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="/aux")])
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["send_message"],
        [
            {
                "chat_id": USER_ID,
                "text": "B",
                "reply_markup": {
                    "inline_keyboard": [[{"text": "C", "callback_data": "action:ae64272b007932d17220d5e5d9870452"}]]
                },
            }
        ],
    )
    bot.method_calls.clear()

    msg_id = bot._latest_message_id_by_chat[USER_ID]
    kwargs = dict(user_id=USER_ID, first_name="User", message_id=msg_id)

    await bot.process_new_updates(
        [tg_update_callback_query(callback_query="action:ae64272b007932d17220d5e5d9870452", **kwargs)]  # type: ignore
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": USER_ID,
                "text": "C",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "E", "callback_data": "action:662f086213b5979b74ad0cd1e4c60416"}],
                        [{"text": "<-", "callback_data": "action:d8f99604d411721de13accee9ca0d745"}],
                    ]
                },
            }
        ],
    )
    bot.method_calls.clear()

    await bot.process_new_updates(
        [tg_update_callback_query(callback_query="action:662f086213b5979b74ad0cd1e4c60416", **kwargs)]  # type: ignore
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": USER_ID,
                "text": "E",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [[{"text": "<-", "callback_data": "action:45e098856e1190fbd9aae06876a57ae9"}]]
                },
            }
        ],
    )
    bot.method_calls.clear()

    await bot.process_new_updates(
        [
            tg_update_callback_query(callback_query="action:45e098856e1190fbd9aae06876a57ae9", **kwargs),  # type: ignore
            tg_update_callback_query(callback_query="action:d8f99604d411721de13accee9ca0d745", **kwargs),  # type: ignore
        ]
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["edit_message_text"],
        [
            {
                "chat_id": USER_ID,
                "text": "C",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "E", "callback_data": "action:662f086213b5979b74ad0cd1e4c60416"}],
                        [{"text": "<-", "callback_data": "action:d8f99604d411721de13accee9ca0d745"}],
                    ]
                },
            },
            {
                "chat_id": USER_ID,
                "text": "B",
                "message_id": msg_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "C", "callback_data": "action:ae64272b007932d17220d5e5d9870452"}],
                    ]
                },
            },
        ],
    )
    bot.method_calls.clear()
