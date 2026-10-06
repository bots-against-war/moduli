<script lang="ts">
  import { t } from "svelte-i18n";
  import { botEventTimestamp, type AnyBotEvent } from "../../api/typeUtils";
  import Timestamp from "../../components/Timestamp.svelte";
  import { loggedInUserStore } from "../../globalStateStores";

  export let events: AnyBotEvent[];
  export let limit: number | null = null;
</script>

{#if events.length !== 0}
  <ol class="relative border-s border-gray-200 mt-2">
    {#each events
      .toSorted((e1, e2) => botEventTimestamp(e2) - botEventTimestamp(e1))
      .slice(0, limit || events.length) as event (event.timestamp)}
      <li class="mb-1 ms-2 p-1">
        <div class="absolute w-2 h-2 bg-gray-300 rounded-full mt-2.5 -start-1 border border-white" />
        <div class="flex flex-row gap-2 items-baseline">
          {#if event.event}
            <span>
              {#if event.event === "started"}
                {$t("dashboard.events.published")}
                {typeof event.version === "number" ? `v${event.version + 1}` : $t("dashboard.events.stub_version")}
              {:else if event.event === "edited"}
                {$t("dashboard.events.created")} v{event.new_version + 1}
              {:else if event.event === "stopped"}
                {$t("dashboard.events.bot_stopped")}
              {/if}
            </span>
          {/if}
          {#if event.timestamp}
            · <Timestamp timestamp={event.timestamp} />
          {/if}
          {#if event.username !== $loggedInUserStore.username}
            · <span class="text-gray-500">@{event.username}</span>
          {/if}
        </div>
      </li>
    {/each}
  </ol>
{/if}
