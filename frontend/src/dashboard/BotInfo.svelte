<script lang="ts">
  import { t, _ } from "svelte-i18n";
  import { Button, Heading } from "flowbite-svelte";
  import { ArrowRightOutline, RocketSolid } from "flowbite-svelte-icons";
  import { updateBotDisplayName } from "../api/botInfo";
  import { removeAlertChatId, setAlertChatId } from "../api/errors";
  import type { BotInfo } from "../api/types";
  import BotUserBadge from "../components/BotUserBadge.svelte";
  import BotVersionInfoBadge from "../components/BotVersionInfoBadge.svelte";
  import GroupChatBadge from "../components/GroupChatBadge.svelte";
  import GroupChatIdSelect from "../components/GroupChatIdSelect.svelte";
  import JumpingIcon from "../components/JumpingIcon.svelte";
  import Navbar from "../components/Navbar.svelte";
  import Page from "../components/Page.svelte";
  import PageContent from "../components/PageContent.svelte";
  import Timestamp from "../components/Timestamp.svelte";
  import BreadcrumbHome from "../components/breadcrumbs/BreadcrumbHome.svelte";
  import Breadcrumbs from "../components/breadcrumbs/Breadcrumbs.svelte";
  import EditableText from "../components/inputs/EditableText.svelte";
  import { errorsPath, formResultsPagePath, settingsPath, studioPath, versionsPagePath } from "../routeUtils";
  import BotInfoCard from "./BotInfoCard.svelte";
  import BotEventList from "./components/BotEventList.svelte";

  export let botInfo: BotInfo;

  const botId = botInfo.bot_id;

  const lastVersionInfo = botInfo.last_versions[botInfo.last_versions.length - 1];
  const runningVersionInfo = botInfo.running_version_info;

  let editedDisplayName = botInfo.display_name;
  let savedAlertChatId = botInfo.alert_chat_id;
  let editedAlertChatId = botInfo.alert_chat_id;
  $: {
    if (editedAlertChatId !== savedAlertChatId) {
      if (editedAlertChatId !== null) {
        setAlertChatId(botId, { alert_chat_id: editedAlertChatId, test: true }).then((res) => {
          if (res.ok) {
            savedAlertChatId = editedAlertChatId;
          }
        });
      } else {
        removeAlertChatId(botId).then((res) => {
          if (res.ok) {
            savedAlertChatId = editedAlertChatId;
          }
        });
      }
    }
  }
</script>

<Page>
  <Navbar />
  <PageContent>
    <Breadcrumbs><BreadcrumbHome /></Breadcrumbs>
    <div class="flex flex-row justify-between items-start gap-2">
      <EditableText bind:value={editedDisplayName} on:edited={() => updateBotDisplayName(botId, editedDisplayName)}>
        <Heading tag="h3">{editedDisplayName}</Heading>
      </EditableText>
      <Button href={studioPath(botId, null)}>
        <strong>{$t("dashboard.to_studio")}</strong>
        <ArrowRightOutline class="w-5 h-5 ml-2" strokeWidth="3" />
      </Button>
    </div>
    <div class="flex flex-row mt-6 gap-5">
      <div class="flex-1 flex flex-col gap-4">
        <BotInfoCard moreLinkHref={versionsPagePath(botId)} moreLinkTitle={$t("dashboard.all_versions")}>
          <div class="flex items-center justify-between pb-3 w-full">
            <span class="text-lg font-bold text-gray-900">{$t("dashboard.status")}</span>
            <div
              class="flex items-center gap-2 px-3 py-2 border {runningVersionInfo !== null
                ? 'text-green-600'
                : 'text-gray-900'}"
            >
              {#if runningVersionInfo !== null}
                <JumpingIcon>
                  <RocketSolid class="w-5 h-5" />
                </JumpingIcon>
                <strong>{$t("dashboard.running")}</strong>
              {:else}
                <RocketSolid class="w-5 h-5" />
                <strong>{$t("dashboard.stopped")}</strong>
              {/if}
            </div>
          </div>
          {#if runningVersionInfo !== null}
            <div class="flex flex-col gap-1 mb-1">
              <span>{$t("dashboard.running_version")}</span>
              <BotVersionInfoBadge ver={runningVersionInfo} />
            </div>
          {/if}
          {#if runningVersionInfo === null || runningVersionInfo.version !== lastVersionInfo.version}
            <div class="flex flex-col gap-1 mb-1">
              <span>
                {$t("dashboard.last_version")}
                {#if runningVersionInfo !== null}
                  (<strong>+{lastVersionInfo.version - runningVersionInfo.version}</strong>)
                {/if}
              </span>
              <BotVersionInfoBadge ver={lastVersionInfo} />
            </div>
          {/if}
        </BotInfoCard>

        <BotInfoCard title={$t("dashboard.account")}>
          <BotUserBadge {botId} />
        </BotInfoCard>

        {#if botInfo.admin_chat_ids.length > 0}
          <BotInfoCard title={$t("dashboard.admin_chats")}>
            <div class="flex flex-col gap-2">
              {#each botInfo.admin_chat_ids as admin_chat_id}
                <GroupChatBadge {botId} chatId={admin_chat_id} />
              {/each}
            </div>
          </BotInfoCard>
        {/if}

        {#if botInfo.forms_with_responses.length > 0}
          <BotInfoCard title={$t("dashboard.form_responses")}>
            {#each botInfo.forms_with_responses as formInfo}
              <div class="border-gray-300 border-l border-b last:border-b-0 px-3 py-4 hover:bg-gray-100">
                <a href={formResultsPagePath(botId, formInfo.form_block_id)} class="flex flex-row justify-between">
                  <span>
                    {#if formInfo.title}
                      {formInfo.title}
                    {:else}
                      "{formInfo.prompt}"
                    {/if}
                  </span>
                  <span class="text-gray-500 text-nowrap">
                    ({formInfo.total_responses})
                  </span>
                </a>
              </div>
            {/each}
          </BotInfoCard>
        {/if}

        <BotInfoCard
          title={$t("dashboard.settings")}
          moreLinkTitle={$t("dashboard.go_to_settings")}
          moreLinkHref={settingsPath(botId)}
        ></BotInfoCard>
      </div>
      <div class="flex-1 flex flex-col gap-4">
        <BotInfoCard title={$t("dashboard.stats")}>
          <strong class="text-2xl">🚧👷🏗️🚧</strong>
          <span>{$t("dashboard.under_construction")}</span>
        </BotInfoCard>

        <BotInfoCard title={$t("dashboard.activity")}>
          <BotEventList events={botInfo.last_events} />
        </BotInfoCard>

        <BotInfoCard
          title={$t("dashboard.bot_errors")}
          moreLinkTitle={$t("dashboard.open_all_errors")}
          moreLinkHref={errorsPath(botId)}
        >
          {#if botInfo.last_errors.length > 0}
            <div class="mb-3">
              {$t("dashboard.last_error")}: <Timestamp
                timestamp={botInfo.last_errors[botInfo.last_errors.length - 1].timestamp}
              />
            </div>
          {/if}
          <GroupChatIdSelect
            label={$t("dashboard.alert_chat")}
            {botId}
            bind:selectedGroupChatId={editedAlertChatId}
            allowNoChat
            forbidLegacyGroups={false}
          >
            <svelte:fragment slot="delete-chat-id-option">{$t("dashboard.disable_alert_chat")}</svelte:fragment>
          </GroupChatIdSelect>
        </BotInfoCard>
      </div>
    </div>
  </PageContent>
</Page>
