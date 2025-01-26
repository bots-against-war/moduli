<script lang="ts">
  import { Accordion, AccordionItem, Heading, Li, List, NumberInput, Select, Toggle } from "flowbite-svelte";
  import { locale, t } from "svelte-i18n";
  import type { HumanOperatorBlock } from "../../../api/types";
  import GroupChatIdSelect from "../../../components/GroupChatIdSelect.svelte";
  import InputWrapper from "../../../components/inputs/InputWrapper.svelte";
  import TextInput from "../../../components/inputs/TextInput.svelte";
  import { TELEGRAM_MAX_MESSAGE_LENGTH_CHARS } from "../../../constants";
  import LocalizableTextInput from "../../components/LocalizableTextInput.svelte";
  import NodeModalBody from "../../components/NodeModalBody.svelte";
  import NodeModalControls from "../../components/NodeModalControls.svelte";
  import { languageConfigStore } from "../../stores";
  import { clone } from "../../utils";
  import { NODE_TITLE_KEY } from "../display";
  import { applyPrefilledMessage, loadPrefilledMessages } from "../FormBlock/prefill";

  export let botId: string; // required for admin chat id rendering, and context does not propagate here
  export let config: HumanOperatorBlock;
  export let onConfigUpdate: (newConfig: HumanOperatorBlock) => any;

  function updateConfig() {
    fhConfig.unanswered_hashtag = unanswered || null;
    fhConfig.anonimyze_users = anonymize == "yes";
    onConfigUpdate({ ...config, feedback_handler_config: fhConfig });
  }

  let fhConfig = clone(config.feedback_handler_config);
  let unanswered = fhConfig.unanswered_hashtag || "";

  const blockSeqClass = "flex flex-col gap-4";
  const blockClass = "flex flex-col gap-2";

  type YesNo = "yes" | "no";
  let anonymize: YesNo = config.feedback_handler_config.anonimyze_users ? "yes" : "no";
  const uaOptions: { value: YesNo; name: string }[] = [
    { value: "yes", name: $t("studio.human_operator.ua_opt_yes") },
    { value: "no", name: $t("studio.human_operator.ua_opt_no") },
  ];

  fhConfig.messages_to_user.throttling = applyPrefilledMessage(
    loadPrefilledMessages(),
    "anti_spam_warning",
    $languageConfigStore,
    $t,
    $locale,
    fhConfig.messages_to_user.throttling,
  );
</script>

<NodeModalBody title={$t(NODE_TITLE_KEY.human_operator)}>
  <div class={blockSeqClass}>
    <div class="flex flex-col gap-6">
      <GroupChatIdSelect
        label={$t("studio.human_operator.admin_chat")}
        {botId}
        bind:selectedGroupChatId={fhConfig.admin_chat_id}
        allowNoChat
      >
        <p slot="description">
          {@html $t("studio.human_operator.admin_chat_descr_1")}
        </p>
      </GroupChatIdSelect>

      <InputWrapper
        label={$t("studio.human_operator.user_anonymization_title")}
        required={false}
        description={$t("studio.human_operator.user_anonymization_descr")}
        let:inputId
      >
        <Select id={inputId} placeholder="" items={uaOptions} bind:value={anonymize} />
        <div class="text-sm text-gray-600">
          {#if anonymize == "yes"}
            {$t("studio.human_operator.user_anonymization_yes_hint")}
          {:else}
            {$t("studio.human_operator.user_anonymization_no_hint")}
          {/if}
        </div>
      </InputWrapper>

      <InputWrapper
        label={$t("studio.human_operator.topics_title")}
        required={false}
        description={$t("studio.human_operator.topics_descr")}
      >
        <Toggle bind:checked={fhConfig.forum_topic_per_user}>{$t("studio.human_operator.topics_turn_on")}</Toggle>
        {#if fhConfig.forum_topic_per_user}
          <div class="text-sm text-gray-600">
            <div>{$t("studio.human_operator.topics_howto_title")}</div>
            <List>
              <Li>{$t("studio.human_operator.topics_howto_p1")}</Li>
              <Li>{$t("studio.human_operator.topics_howto_p2")}</Li>
            </List>
          </div>
        {/if}
      </InputWrapper>

      <LocalizableTextInput
        label={$t("studio.human_operator.reponse_title")}
        placeholder={$t("studio.human_operator.reponse_placeholder")}
        bind:value={fhConfig.messages_to_user.forwarded_to_admin_ok}
        maxCharacters={TELEGRAM_MAX_MESSAGE_LENGTH_CHARS}
      />
    </div>

    <Accordion flush>
      <AccordionItem paddingDefault="p-3" flush>
        <span slot="header">{$t("studio.human_operator.more_settings")}</span>
        <div class={blockSeqClass}>
          <div class={blockClass}>
            <Heading tag="h6">{$t("studio.human_operator.admin_msgs")}</Heading>
            <TextInput
              label={$t("studio.human_operator.admin_reply_ok_label")}
              placeholder={$t("studio.human_operator.admin_reply_ok_placeholder")}
              bind:value={fhConfig.messages_to_admin.copied_to_user_ok}
            />
            <TextInput
              label={$t("studio.human_operator.admin_reply_undo_title")}
              placeholder={$t("studio.human_operator.admin_reply_undo_placeholder")}
              bind:value={fhConfig.messages_to_admin.deleted_message_ok}
            />
            <TextInput
              label={$t("studio.human_operator.admin_reply_failed_to_undo_title")}
              placeholder={$t("studio.human_operator.admin_reply_failed_to_undo_placeholder")}
              bind:value={fhConfig.messages_to_admin.can_not_delete_message}
            />
          </div>
          <div class={blockClass}>
            <Heading tag="h6">{$t("studio.human_operator.anti_spam_title")}</Heading>
            <InputWrapper
              label={$t("studio.human_operator.anti_spam_msg_per_min")}
              description={$t("studio.human_operator.anti_spam_msg_per_min_descr")}
            >
              <NumberInput bind:value={fhConfig.max_messages_per_minute} min={1} max={60} step={1} type="number" />
            </InputWrapper>

            <LocalizableTextInput
              label={$t("studio.human_operator.anti_spam_warning_title")}
              placeholder={$t("studio.human_operator.anti_spam_warning_placeholder")}
              bind:value={fhConfig.messages_to_user.throttling}
              maxCharacters={TELEGRAM_MAX_MESSAGE_LENGTH_CHARS}
            />
          </div>
        </div>
      </AccordionItem>
    </Accordion>
  </div>
  <NodeModalControls on:save={updateConfig} />
</NodeModalBody>
