<script lang="ts">
  import truncate from "@svackages/truncate";
  import { type BotVersionInfo } from "../api/types";
  import Timestamp from "./Timestamp.svelte";
  import { loggedInUserStore } from "../globalStateStores";

  export let ver: BotVersionInfo;
  export let carded: boolean = true;
</script>

<div class="p-1 ${carded ? 'border-gray-200 border bg-gray-100' : ''}">
  <div>
    <strong>v{ver.version + 1}</strong>
    {#if ver.metadata.timestamp}
      · <Timestamp timestamp={ver.metadata.timestamp} timeClass="text-gray-500" />
    {/if}
    {#if ver.metadata.author_username !== $loggedInUserStore.username}
      · <span class="text-gray-500">@{ver.metadata.author_username}</span>
    {/if}
  </div>
  {#if ver.metadata.message}
    {#if carded}
      <p use:truncate class="text-gray-600 text-sm max-h-4">{ver.metadata.message}</p>
    {:else}
      <p class="text-gray-600 text-sm">{ver.metadata.message}</p>
    {/if}
  {/if}
</div>
