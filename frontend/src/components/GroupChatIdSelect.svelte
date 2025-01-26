<script lang="ts">
  import { Accordion, AccordionItem, Li, List, Spinner } from "flowbite-svelte";
  import { CloseOutline, ExclamationCircleOutline, PenOutline, TrashBinOutline } from "flowbite-svelte-icons";
  import { onDestroy } from "svelte";
  import { t } from "svelte-i18n";
  import { getAvailableGroupChats, startGroupChatDiscovery, stopGroupChatDiscovery } from "../api/groupChats";
  import type { TgGroupChat } from "../api/types";
  import ErrorBadge from "./AlertBadge.svelte";
  import BotUserBadge from "./BotUserBadge.svelte";
  import GroupChatBadge from "./GroupChatBadge.svelte";
  import InputWrapper from "./inputs/InputWrapper.svelte";

  export let label: string;
  export let botId: string;
  export let selectedGroupChatId: number | string | null;
  export let forbidLegacyGroups: boolean = true;
  export let allowNoChat: boolean = false;
  export let description: string | null = null;

  // auto-open if not selected initially
  let isOpen = !allowNoChat && selectedGroupChatId === null;

  let chatsLoadError: string | null = null;
  let availableChats: TgGroupChat[] = [];
  async function loadAvailableGroupChats() {
    const res = await getAvailableGroupChats(botId);
    if (res.ok) {
      chatsLoadError = null;
      availableChats = res.data;
    } else {
      chatsLoadError = res.error;
      availableChats = [];
      console.error("Error retrieving available group chats: ", res.error);
    }
  }

  let availableGroupChatsLoadedPromise: Promise<void> = new Promise((resolve, _) => resolve());

  $: {
    if (isOpen) {
      availableGroupChatsLoadedPromise = loadAvailableGroupChats();
      startScanning();
    } else {
      // on any close of the accordion we make sure to stop the discovery
      stopScanning();
    }
  }
  let isScannning = false;
  let discoverChatsPollingIntervalId: number | null = null;
  let stopChatDiscoveryAfterTimeoutId: number | null = null;
  async function stopScanning() {
    if (!isScannning) return;
    discoverChatsPollingIntervalId !== null ? clearInterval(discoverChatsPollingIntervalId) : null;
    stopChatDiscoveryAfterTimeoutId !== null ? clearTimeout(stopChatDiscoveryAfterTimeoutId) : null;
    await stopGroupChatDiscovery(botId);
    isScannning = false;
  }
  async function startScanning() {
    if (isScannning) return;
    isScannning = true;
    await startGroupChatDiscovery(botId);

    // update available group list each 5 seconds
    // @ts-expect-error
    discoverChatsPollingIntervalId = setInterval(async () => {
      if (isScannning) {
        console.debug("Updating available group chats list");
        await loadAvailableGroupChats();
      } else if (discoverChatsPollingIntervalId !== null) {
        clearInterval(discoverChatsPollingIntervalId);
      }
    }, 5 * 1000);
    // auto-stop discovery after 10 minutes
    // @ts-expect-error
    stopChatDiscoveryAfterTimeoutId = setTimeout(stopScanning, 10 * 60 * 1000);
  }
  onDestroy(stopScanning);

  const chatLabel = (chat: TgGroupChat) => `group-chat-${chat.id}`;
</script>

<InputWrapper {label} {description} required={!allowNoChat}>
  <Accordion flush>
    <AccordionItem
      bind:open={isOpen}
      paddingFlush="pb-2"
      borderBottomClass="border-none"
      class="flex items-center justify-between w-full font-medium text-left border-none"
    >
      <div slot="header" class="text-gray-900 text-sm">
        {#if selectedGroupChatId !== null}
          <GroupChatBadge {botId} chatId={selectedGroupChatId} />
        {:else}
          <span class="text-gray-600">{$t("components.group_chat_select.not_selected")}</span>
        {/if}
      </div>
      <div slot="arrowdown">
        <PenOutline size="sm" />
      </div>
      <div slot="arrowup">
        <CloseOutline size="sm" />
      </div>

      <!-- accordion body -->
      <div class="text-sm font-medium text-gray-900 p-2 bg-gray-50">
        <div class="gap-2">
          <slot name="description" />
          <slot name="howto">
            <details class="my-2">
              <summary>{$t("components.group_chat_select.how_to.title")}</summary>
              <List tag="ol">
                <Li>
                  {$t("components.group_chat_select.how_to.step_1_1")} (<BotUserBadge {botId} inline let:user
                    ><code>@{user.username}</code></BotUserBadge
                  >) {$t("components.group_chat_select.how_to.step_1_2")}
                </Li>
                {#if forbidLegacyGroups}
                  <Li>
                    {$t("components.group_chat_select.how_to.step_2")}
                  </Li>
                {/if}
                <Li>{$t("components.group_chat_select.how_to.step_3")}</Li>
                <Li>
                  {$t("components.group_chat_select.how_to.step_4")}
                  <BotUserBadge {botId} inline let:user><code>/discover_chat@{user.username}</code></BotUserBadge>
                </Li>
              </List>
            </details>
          </slot>
        </div>

        {#await availableGroupChatsLoadedPromise}
          <Spinner />
        {:then}
          {#if chatsLoadError !== null}
            <ErrorBadge
              title={$t("components.group_chat_select.error_loading_available_chats")}
              text={chatsLoadError}
            />
          {:else}
            <div class="flex flex-col gap-1">
              <div class="font-bold">{$t("components.group_chat_select.available_chats")}</div>
              <div class="flex flex-col gap-2">
                {#each availableChats as chat (chat.id)}
                  <div class="flex flex-row items-center gap-2">
                    <input
                      type="radio"
                      id={chatLabel(chat)}
                      bind:group={selectedGroupChatId}
                      on:change={async () => {
                        isOpen = false;
                      }}
                      value={chat.id}
                      disabled={forbidLegacyGroups && chat.type === "group"}
                    />
                    {#if forbidLegacyGroups && chat.type === "group"}
                      <ExclamationCircleOutline
                        color="red"
                        title={{
                          id: "non-supergroup chat is forbidden",
                          title: $t("components.group_chat_select.chat_must_be_a_supergroup"),
                        }}
                      />
                    {/if}
                    <label
                      for={chatLabel(chat)}
                      class={forbidLegacyGroups && chat.type === "group" ? "opacity-50" : ""}
                    >
                      <GroupChatBadge {botId} chatId={chat.id} chatData={chat} />
                    </label>
                  </div>
                {/each}
              </div>
              {#if allowNoChat && (availableChats.length > 0 || selectedGroupChatId !== null)}
                <div class="flex flex-row items-center gap-2">
                  <input
                    type="radio"
                    id={"delete-chat-id"}
                    on:change={async () => {
                      selectedGroupChatId = null;
                      isOpen = false;
                    }}
                    value={"delete-chat-id"}
                  />
                  <label for={"delete-chat-id"} class="flex flex-row gap-1">
                    <slot name="delete-chat-id-option">
                      <TrashBinOutline size="sm" />
                      {$t("generic.delete")}
                    </slot>
                  </label>
                </div>
              {/if}
              {#if isScannning}
                <p class="mt-3">
                  <Spinner size={4} class="mr-2" />
                  {$t("components.group_chat_select.searching")}
                </p>
              {/if}
            </div>
          {/if}
        {/await}
      </div>
    </AccordionItem>
  </Accordion>
</InputWrapper>
