import type { MenuMechanism, UserFlowBlockConfig, UserFlowConfig, UserFlowEntryPointConfig } from "../../api/types";
import type { I18NLocale, MessageFormatter } from "../../i18n";
import type { LanguageConfig } from "../stores";
import { loadPrefilledMessages, prefilledMessage, type PrefillableKey } from "./FormBlock/prefill";

export type ConfigFactory = (
  id: string,
  t: MessageFormatter,
  langConfig: LanguageConfig | null,
  currentConfig: UserFlowConfig,
  locale: I18NLocale,
) => UserFlowEntryPointConfig | UserFlowEntryPointConfig;

export const defaultCommandEntrypoint: ConfigFactory = (id: string): UserFlowEntryPointConfig => {
  return {
    command: {
      entrypoint_id: id,
      command: "command",
      scope: "private",
      short_description: null,
      next_block_id: null,
    },
  };
};

export const defaultContentBlockConfig: ConfigFactory = (id: string, t: MessageFormatter): UserFlowBlockConfig => {
  return {
    content: {
      block_id: id,
      contents: [{ text: { text: t("studio.defaults.text_content"), markup: "markdown" }, attachments: [] }],
      next_block_id: null,
    },
  };
};

export const defaultHumanOperatorBlockConfig: ConfigFactory = (
  id: string,
  t: MessageFormatter,
  langConfig: LanguageConfig | null,
  _: UserFlowConfig,
  locale: I18NLocale,
): UserFlowBlockConfig => {
  return {
    human_operator: {
      block_id: id,
      catch_all: false,
      feedback_handler_config: {
        admin_chat_id: null,
        forum_topic_per_user: false,
        anonimyze_users: true,
        max_messages_per_minute: 10,
        messages_to_user: {
          forwarded_to_admin_ok: "",
          throttling: prefilledMessage(loadPrefilledMessages(), "anti_spam_warning", langConfig, locale),
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
};

export const defaultMenuBlockConfig: ConfigFactory = (
  id: string,
  _: MessageFormatter,
  langConfig: LanguageConfig | null,
  currentConfig: UserFlowConfig,
): UserFlowBlockConfig => {
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
};

export const defaultLanguageSelectBlockConfig: ConfigFactory = (id: string): UserFlowBlockConfig => {
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
};

export function generateFormName(): string {
  return `form-${crypto.randomUUID()}`;
}

export const defaultFormBlockConfig: ConfigFactory = (
  id: string,
  t: MessageFormatter,
  langConfig: LanguageConfig | null,
  _: UserFlowConfig,
  locale: I18NLocale,
): UserFlowBlockConfig => {
  const pm = loadPrefilledMessages();
  const prefilledMessage_ = (key: PrefillableKey) => prefilledMessage(pm, key, langConfig, locale);
  return {
    form: {
      block_id: id,
      members: [],
      form_name: generateFormName(),
      messages: {
        form_start: "",
        field_is_skippable: prefilledMessage_("field_is_skippable"),
        field_is_not_skippable: prefilledMessage_("field_is_not_skippable"),
        please_enter_correct_value: prefilledMessage_("please_enter_correct_value"),
        unsupported_command: prefilledMessage_("unsupported_command"),
        cancel_command_is: prefilledMessage_("cancel_command_is"),
      },
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
};
