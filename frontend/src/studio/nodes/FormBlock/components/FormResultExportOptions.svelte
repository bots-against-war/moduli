<script lang="ts">
  import { Select, Toggle } from "flowbite-svelte";
  import { t } from "svelte-i18n";
  import type { FormResultUserAttribution, FormResultsExport } from "../../../../api/types";
  import GroupChatIdSelect from "../../../../components/GroupChatIdSelect.svelte";
  import InputWrapper from "../../../../components/inputs/InputWrapper.svelte";
  import BlockNameInline from "../../../components/BlockNameInline.svelte";
  import { NodeTypeKey } from "../../display";

  export let config: FormResultsExport;
  export let botId: string;

  const userAttributionOptions: { value: FormResultUserAttribution; name: string }[] = [
    { value: "none", name: $t("studio.form.do_not_save_user") },
    { value: "unique_id", name: $t("studio.form.save_anonymous") },
    { value: "name", name: $t("studio.form.only_tg_name") },
    { value: "full", name: $t("studio.form.tg_name_and_account") },
  ];
</script>

<div class="flex flex-col gap-5">
  <div class="flex flex-col gap-3">
    <h3 class="font-bold">{$t("studio.form.personal_data")}</h3>
    <Select placeholder="" items={userAttributionOptions} bind:value={config.user_attribution} />
    <div class="text-sm text-gray-600">
      {#if config.user_attribution == "none"}
        {$t("studio.form.do_not_save_user_descr")}
      {:else if config.user_attribution == "unique_id"}
        {$t("studio.form.save_anonymous_descr")}
      {:else if config.user_attribution == "name"}
        {$t("studio.form.only_tg_name_descr")}
      {:else if config.user_attribution == "full"}
        {$t("studio.form.tg_name_and_account_descr")}
      {/if}
    </div>
  </div>
  <div class="flex flex-col gap-3">
    <h3 class="font-bold">{$t("studio.form.responses")}</h3>
    <Toggle bind:checked={config.echo_to_user}>{$t("studio.form.responses_send_to_user")}</Toggle>
    <Toggle bind:checked={config.to_store}>{$t("studio.form.responses_save_to_store")}</Toggle>
    <div class="flex flex-col gap-1">
      <Toggle
        checked={config.to_chat !== null}
        on:change={(e) => {
          // @ts-expect-error
          if (e.target.checked) {
            config.to_chat = { chat_id: null, via_feedback_handler: false };
          } else {
            config.to_chat = null;
          }
        }}>{$t("studio.form.responses_send_to_chat")}</Toggle
      >
      {#if config.to_chat}
        <div class="p-2 m-2 border-l-2 border-grey-600 flex flex-col gap-3">
          <GroupChatIdSelect
            label={$t("studio.form.chat")}
            description={$t("studio.form.chat_descr")}
            {botId}
            bind:selectedGroupChatId={config.to_chat.chat_id}
            forbidLegacyGroups={false}
            allowNoChat
          />
          <InputWrapper label={$t("studio.form.chat_feedback_mode")} required={false}>
            <Toggle bind:checked={config.to_chat.via_feedback_handler}>{$t("studio.form.chat_feedback_mode_on")}</Toggle
            >
            {#if config.to_chat.via_feedback_handler}
              <div class="text-sm text-gray-700">
                {$t("studio.form.chat_feedback_mode_warning")}
                <BlockNameInline key={NodeTypeKey.human_operator} />!
              </div>
            {/if}
          </InputWrapper>
        </div>
      {/if}
    </div>
  </div>
</div>
