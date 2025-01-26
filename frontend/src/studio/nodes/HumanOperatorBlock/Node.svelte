<script lang="ts">
  import { t } from "svelte-i18n";
  import { Node } from "svelvet";
  import type { HumanOperatorBlock } from "../../../api/types";
  import GroupChatBadge from "../../../components/GroupChatBadge.svelte";
  import type { SvelvetPosition } from "../../../types";
  import { getModalOpener } from "../../../utils";
  import InputAnchor from "../../components/InputAnchor.svelte";
  import NodeContent from "../../components/NodeContent.svelte";
  import { NodeTypeKey } from "../display";
  import { DEFAULT_NODE_PROPS } from "../nodeProps";
  import { validateHumanOperatorBlock } from "../nodeValidators";
  import Modal from "./Modal.svelte";

  const openModal = getModalOpener();

  export let config: HumanOperatorBlock;
  export let position: SvelvetPosition;
  export let isValid = true;
  export let botId: string;

  const setNewConfig = (newConfig: HumanOperatorBlock) => {
    config = newConfig;
  };

  function openEditModal() {
    openModal(Modal, {
      config,
      botId,
      onConfigUpdate: setNewConfig,
    });
  }
</script>

<Node id={config.block_id} bind:position {...DEFAULT_NODE_PROPS}>
  <InputAnchor />
  <NodeContent
    id={config.block_id}
    key={NodeTypeKey.human_operator}
    bind:isValid
    {config}
    configValidator={validateHumanOperatorBlock}
    on:delete
    on:clone
    on:edit={openEditModal}
  >
    {#if config.feedback_handler_config.admin_chat_id !== null}
      <GroupChatBadge {botId} chatId={config.feedback_handler_config.admin_chat_id} />
    {:else}
      {$t("studio.human_operator.in_private_messages")}
    {/if}
  </NodeContent>
</Node>
