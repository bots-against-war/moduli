import type {
  FormMessages,
  MenuMechanism,
  UserFlowBlockConfig,
  UserFlowConfig,
  UserFlowEntryPointConfig,
} from "../../api/types";
import type { MessageFormatter } from "../../i18n";
import type { LanguageConfig } from "../stores";
import { updateWithPrefilled } from "./FormBlock/prefill";

export type ConfigFactory = (
  id: string,
  t: MessageFormatter,
  langConfig: LanguageConfig | null,
  currentConfig: UserFlowConfig,
) => UserFlowEntryPointConfig | UserFlowEntryPointConfig;

export function defaultCommandEntrypoint(id: string): UserFlowEntryPointConfig {
  return {
    command: {
      entrypoint_id: id,
      command: "command",
      scope: "private",
      short_description: null,
      next_block_id: null,
    },
  };
}

export function defaultContentBlockConfig(id: string, t: MessageFormatter): UserFlowBlockConfig {
  return {
    content: {
      block_id: id,
      contents: [{ text: { text: t("studio.defaults.text_content"), markup: "markdown" }, attachments: [] }],
      next_block_id: null,
    },
  };
}

export const PLACEHOLDER_GROUP_CHAT_ID = 0;

export function defaultHumanOperatorBlockConfig(id: string, t: MessageFormatter): UserFlowBlockConfig {
  return {
    human_operator: {
      block_id: id,
      catch_all: false,
      feedback_handler_config: {
        admin_chat_id: PLACEHOLDER_GROUP_CHAT_ID,
        forum_topic_per_user: false,
        anonimyze_users: true,
        max_messages_per_minute: 10,
        messages_to_user: {
          forwarded_to_admin_ok: "",
          throttling: t("studio.defaults.throttling_msg"),
        },
        messages_to_admin: {
          copied_to_user_ok: t("studio.defaults.copied_to_user"),
          deleted_message_ok: t("studio.defaults.deleted_message"),
          can_not_delete_message: t("studio.defaults.failed_to_delete"),
        },
        hashtags_in_admin_chat: false,
        hashtag_message_rarer_than: null,
        unanswered_hashtag: null,
        message_log_to_admin_chat: true,
      },
    },
  };
}

export function defaultMenuBlockConfig(
  id: string,
  _: MessageFormatter,
  langConfig: LanguageConfig | null,
  currentConfig: UserFlowConfig,
): UserFlowBlockConfig {
  const topMechanismOccurrences = currentConfig.blocks
    .map((bc) => (bc.menu ? bc.menu.menu.config.mechanism : null))
    .filter((mb) => mb !== null)
    .reduce((acc, m) => acc.set(m, (acc.get(m) || 0) + 1), new Map<MenuMechanism, number>())
    .entries()
    .toArray()
    .toSorted(([m1, o1], [m2, o2]) => o1 - o2);

  const mechanism: MenuMechanism =
    topMechanismOccurrences.length > 0 ? topMechanismOccurrences[0][0] : "inline_buttons";

  return {
    menu: {
      block_id: id,
      menu: {
        text: "",
        markup: "markdown",
        items: [],
        config: {
          back_label:
            langConfig === null
              ? "⬅️⬅️⬅️"
              : Object.fromEntries(langConfig.supportedLanguageCodes.map((lang) => [lang, "⬅️⬅️⬅️"])),
          mechanism: mechanism,
          lock_after_termination: false,
        },
      },
    },
  };
}

export function defaultLanguageSelectBlockConfig(id: string): UserFlowBlockConfig {
  return {
    language_select: {
      block_id: id,
      menu_config: {
        propmt: {},
        is_blocking: false,
        emoji_buttons: true,
      },
      supported_languages: [],
      default_language: "",
      language_selected_next_block_id: null,
    },
  };
}

export function generateFormName(): string {
  return `form-${crypto.randomUUID()}`;
}

export function defaultFormBlockConfig(
  id: string,
  _: MessageFormatter,
  langConfig: LanguageConfig | null,
): UserFlowBlockConfig {
  let messages: FormMessages = {
    form_start: "",
    field_is_skippable: "",
    field_is_not_skippable: "",
    please_enter_correct_value: "",
    unsupported_command: "",
    cancel_command_is: "",
  };
  [messages] = updateWithPrefilled(messages, langConfig);
  return {
    form: {
      block_id: id,
      members: [],
      form_name: generateFormName(),
      messages: messages,
      results_export: {
        user_attribution: "none",
        echo_to_user: true,
        to_chat: null,
        to_store: false,
      },
      form_cancelled_next_block_id: null,
      form_completed_next_block_id: null,
    },
  };
}
