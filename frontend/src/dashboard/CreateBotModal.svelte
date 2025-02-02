<script lang="ts">
  import { A, Button, Li, List } from "flowbite-svelte";
  import { t } from "svelte-i18n";
  import { navigate } from "svelte-routing";
  import { saveBotConfig } from "../api/botConfig";
  import type { BotConfig } from "../api/types";
  import { validateBotToken } from "../api/validation";
  import ErrorBadge from "../components/AlertBadge.svelte";
  import ButtonLoadingSpinner from "../components/ButtonLoadingSpinner.svelte";
  import PasswordInput from "../components/inputs/PasswordInput.svelte";
  import { BOT_INFO_NODE_ID, DEFAULT_START_COMMAND_ENTRYPOINT_ID } from "../constants";
  import { dashboardPath } from "../routeUtils";
  import { createBotTokenSecret, getError, getModalCloser, unwrap } from "../utils";

  const closeModal = getModalCloser();

  let botTokenInput = "";
  let errorTitle: string | null = null;
  let error: string | null = null;
  let isCreating = false;
  let userClickedCreate = false;

  async function createNewBot() {
    userClickedCreate = true;
    errorTitle = null;
    error = null;
    try {
      isCreating = true;
      await createNewBotInner();
    } finally {
      isCreating = false;
    }
  }

  async function createNewBotInner() {
    let botToken = botTokenInput.trim();
    if (!botToken) {
      return;
    }

    let validationResult = await validateBotToken(botToken);
    if (!validationResult.ok) {
      error = $t("listing.newbot.incorrect_token_error");
      return;
    }
    const tokenValidationResult = validationResult.data;
    if (tokenValidationResult.is_used) {
      error = $t("listing.newbot.already_used_token_error");
      return;
    }

    const botDisplayName = tokenValidationResult.name;

    let newTokenSecretRes = await createBotTokenSecret(tokenValidationResult.suggested_bot_id, botToken);
    let newTokenSaveErr = getError(newTokenSecretRes);
    if (newTokenSaveErr !== null) {
      errorTitle = $t("listing.newbot.failed_to_save_token_error");
      error = newTokenSaveErr;
      return;
    }

    const config: BotConfig = {
      token_secret_name: unwrap(newTokenSecretRes),
      user_flow_config: {
        entrypoints: [
          {
            command: {
              entrypoint_id: DEFAULT_START_COMMAND_ENTRYPOINT_ID,
              command: "start",
              short_description: $t("listing.newbot.start_cmd_description"),
              next_block_id: null,
            },
          },
        ],
        blocks: [],
        node_display_coords: Object.fromEntries([
          [DEFAULT_START_COMMAND_ENTRYPOINT_ID, { x: 0, y: 0 }],
          [BOT_INFO_NODE_ID, { x: 0, y: -150 }],
        ]),
      },
    };
    const saveBotResult = await saveBotConfig(tokenValidationResult.suggested_bot_id, {
      config,
      start: false,
      version_message: null,
      display_name: botDisplayName,
    });

    if (saveBotResult.ok) {
      error = null;
      navigate(dashboardPath(tokenValidationResult.suggested_bot_id));
      closeModal();
    } else if (!saveBotResult.ok) {
      errorTitle = $t("listing.newbot.generic_saving_error");
      error = getError(saveBotResult);
    }
  }
</script>

<div class="flex flex-col gap-4">
  <PasswordInput
    bind:value={botTokenInput}
    label={$t("listing.newbot.token")}
    error={userClickedCreate && !botTokenInput ? $t("listing.newbot.token_cannot_be_empty_error") : null}
    placeholder="123456789:ABCDEFGHIJKLMOPQRSTUVWXYZabcdefghij"
  >
    <svelte:fragment slot="description">
      <p>{$t("listing.newbot.howto.p1")}</p>
      <List class="mb-2 marker:text-gray-600">
        <Li>{$t("listing.newbot.howto.p2")} <A href="https://t.me/BotFather">@BotFather</A></Li>
        <Li>{$t("listing.newbot.howto.p3")} <code>/newbot</code></Li>
        <Li>{$t("listing.newbot.howto.p4")}</Li>
        <Li>{$t("listing.newbot.howto.p5")}</Li>
      </List>
    </svelte:fragment>
  </PasswordInput>
  {#if error !== null}
    <ErrorBadge title={errorTitle || $t("listing.newbot.generic_error")} text={error} />
  {/if}
  <div>
    <Button on:click={createNewBot}>
      <ButtonLoadingSpinner loading={isCreating} />
      {$t("listing.create")}
    </Button>
    <Button outline on:click={closeModal}>{$t("generic.cancel")}</Button>
  </div>
</div>
