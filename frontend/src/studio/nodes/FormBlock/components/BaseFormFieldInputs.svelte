<script lang="ts">
  import { t } from "svelte-i18n";
  import { Toggle } from "flowbite-svelte";
  import type { BaseFormFieldConfig } from "../../../../api/types";
  import EditableText from "../../../../components/inputs/EditableText.svelte";
  import { TELEGRAM_MAX_MESSAGE_LENGTH_CHARS } from "../../../../constants";
  import LocalizableTextInput from "../../../components/LocalizableTextInput.svelte";
  import { languageConfigStore } from "../../../stores";
  import { localizableTextToString } from "../../../utils";
  import { getRandomContent as getRandomFormExampleContent } from "../content";
  export let config: BaseFormFieldConfig;

  let exampleContent = getRandomFormExampleContent($t);
  let syncNameWithPrompt = config.name === localizableTextToString(config.prompt, $languageConfigStore);
  $: {
    if (syncNameWithPrompt) {
      config.name = localizableTextToString(config.prompt, $languageConfigStore);
    }
  }
</script>

<div class="flex flex-col gap-1">
  <EditableText
    bind:value={config.name}
    on:startedEditing={() => {
      syncNameWithPrompt = false;
    }}
    on:edited={() => {
      // forbid just deleting the name!
      if (config.name.length == 0) {
        syncNameWithPrompt = true;
      }
    }}
  >
    {#if config.is_required}
      <span class="text-red-700">*</span>
    {/if}
    {config.name}
  </EditableText>
  <LocalizableTextInput
    placeholder={exampleContent.prompt}
    bind:value={config.prompt}
    maxCharacters={TELEGRAM_MAX_MESSAGE_LENGTH_CHARS}
    on:languageChanged
  />
  <Toggle bind:checked={config.is_required} size="small">{$t("studio.form.required")}</Toggle>
</div>
