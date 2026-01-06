<script lang="ts">
  import { Button, Heading, Spinner, Tooltip } from "flowbite-svelte";
  import { QuestionCircleOutline } from "flowbite-svelte-icons";
  import { locale, t } from "svelte-i18n";
  import { navigate } from "svelte-routing";
  import { Svelvet } from "svelvet";
  import { saveBotConfig } from "../api/botConfig";
  import { getBlockId, getEntrypointId } from "../api/typeUtils";
  import type { BotConfig, UserFlowConfig } from "../api/types";
  import Navbar from "../components/Navbar.svelte";
  import GridPlusColored from "../components/icons/GridPlusColored.svelte";
  import { BOT_INFO_NODE_ID } from "../constants";
  import { dashboardPath } from "../routeUtils";
  import {
    INFO_MODAL_OPTIONS,
    err,
    getError,
    getModalOpener,
    ok,
    sleep,
    withConfirmation,
    type Result,
  } from "../utils";
  import ReadmeModal from "./ReadmeModal.svelte";
  import SaveConfigModal from "./SaveConfigModal.svelte";
  import TemplatesModal from "./TemplatesModal.svelte";
  import AddNodeButton from "./components/AddNodeButton.svelte";
  import DeletableEdge from "./components/DeletableEdge.svelte";
  import StudioSidePandel from "./components/StudioSidePanel.svelte";
  import BotInfoNode from "./nodes/BotInfo/Node.svelte";
  import CommandEntryPointNode from "./nodes/CommandEntryPoint/Node.svelte";
  import ContentBlockNode from "./nodes/ContentBlock/Node.svelte";
  import FormNode from "./nodes/FormBlock/Node.svelte";
  import HumanOperatorNode from "./nodes/HumanOperatorBlock/Node.svelte";
  import LanguageSelectNode from "./nodes/LanguageSelectBlock/Node.svelte";
  import MenuNode from "./nodes/MenuBlock/Node.svelte";
  import {
    defaultCommandEntrypoint,
    defaultContentBlockConfig,
    defaultFormBlockConfig,
    defaultHumanOperatorBlockConfig,
    defaultLanguageSelectBlockConfig,
    defaultMenuBlockConfig,
    type ConfigFactory,
  } from "./nodes/defaultConfigs";
  import { NODE_HUE, NODE_ICON, NODE_TITLE_KEY, NodeTypeKey, headerColor } from "./nodes/display";
  import { languageConfigStore } from "./stores";
  import { applyTemplate, basicShowcaseTemplate, type Template } from "./templates";
  import {
    NodeKind,
    areEqual,
    clone,
    cloneBlockConfig,
    cloneEntrypointConfig,
    filterNodeDisplayCoords,
    generateNodeId,
    type TentativeNode,
  } from "./utils";

  const open = getModalOpener();
  const README_SHOWN_LS_KEY = "readmeShown";

  export let botId: string;
  export let botConfig: BotConfig;
  export let readonly: boolean;

  const workingCopyLSKey = `configWorkingCopy-${botId}`;

  let ufConfig = botConfig.user_flow_config;
  let savedUfConfig = clone(ufConfig);
  const oldWorkingCopyUfConfigJson = localStorage.getItem(workingCopyLSKey);

  // region: reactive logic

  let forceRerenderCounter = 0;
  const forceRerender = () => {
    console.debug("Forcing rerender of the graph");
    forceRerenderCounter += 1;
  };

  let isModified = false;
  let isMultilang = false;

  const EDIT_HISTORY_LENGTH = 30;
  const editHistory: UserFlowConfig[] = [clone(ufConfig)];
  let lastEditTime = Date.now();

  let saveWorkingCopyScheduled: boolean = false;
  const saveWorkingCopy = async () => {
    if (saveWorkingCopyScheduled) return;
    saveWorkingCopyScheduled = true;
    await sleep(100); // debounce: avoid rapid consecutive saves
    localStorage.setItem(workingCopyLSKey, JSON.stringify(ufConfig));
    console.debug("Working copy saved");
    saveWorkingCopyScheduled = false;
  };
  const deleteWorkingCopy = () => localStorage.removeItem(workingCopyLSKey);

  $: {
    // reactive block running on every config update
    // do not rely on it to be too precise, sometimes it fires more that one would expect
    // add manual debouncing, if needed

    isModified = !areEqual(ufConfig, savedUfConfig);
    console.debug(`isModified = ${isModified}`);

    if (!areEqual(ufConfig, editHistory[editHistory.length - 1])) {
      const now = Date.now();
      if (now - lastEditTime > 300) {
        editHistory.push(clone(ufConfig));
        console.debug("Pushed to edit history", editHistory[editHistory.length - 1]);
        lastEditTime = now;
        if (editHistory.length > EDIT_HISTORY_LENGTH) {
          editHistory.splice(0, editHistory.length - EDIT_HISTORY_LENGTH);
        }
      } else {
        // debouncing rapid changes in config, e.g. when the block is deleted and "next_block_id" in other blocks gets deleted
        editHistory[editHistory.length - 1] = clone(ufConfig);
        console.debug("Updated the last edit history entry", editHistory[editHistory.length - 1]);
      }
    }

    saveWorkingCopy();

    let newIsMultilang = false;
    for (const block of ufConfig.blocks) {
      if (block.language_select) {
        newIsMultilang = true;
        if (block.language_select.supported_languages.length > 0) {
          languageConfigStore.set({
            supportedLanguageCodes: block.language_select.supported_languages,
            defaultLanguageCode: block.language_select.default_language,
          });
        }
        break;
      }
    }
    if (!newIsMultilang) {
      languageConfigStore.set(null);
    }
    if (newIsMultilang !== isMultilang) {
      forceRerender();
      isMultilang = newIsMultilang;
    }
  }

  function undo() {
    if (editHistory.length < 2) {
      window.alert("Already at the earliest change");
      return;
    }
    console.debug("Undoing the last change...");
    editHistory.pop(); // removing the last version from the edit history
    const undoneUfConfig = editHistory[editHistory.length - 1];
    undoneUfConfig.node_display_coords = filterNodeDisplayCoords(ufConfig.node_display_coords, undoneUfConfig);
    ufConfig = clone(undoneUfConfig);
    forceRerender();
  }

  // region: node manipulation

  function deleteNode(event: CustomEvent<string>) {
    const id = event.detail;
    // this is a bit cumbersome because we store very similar things (blocks and entrypoing) in two different places
    // as a result we need to look in two places and process every one of them
    const entrypointIdx = ufConfig.entrypoints.map(getEntrypointId).findIndex((nodeId) => nodeId === id);
    const blockIdx = ufConfig.blocks.map(getBlockId).findIndex((nodeId) => nodeId === id);
    if (entrypointIdx !== -1) {
      console.debug(`Deleting entrypoint id=${id} idx=${entrypointIdx}`, ufConfig.entrypoints[entrypointIdx]);
      ufConfig.entrypoints = ufConfig.entrypoints.toSpliced(entrypointIdx, 1);
    } else if (blockIdx !== -1) {
      console.debug(`Deleting block id=${id} idx=${blockIdx}`, ufConfig.blocks[blockIdx]);
      ufConfig.blocks = ufConfig.blocks.toSpliced(blockIdx, 1);
    } else {
      console.debug(`Node with id '${id}' not found among entrypoints and blocks`);
      return;
    }
  }

  // when the user clicks on "add" button for a particular kind of node, we save it as "tentative"
  // then, when the user selects a place for the node, we add it to the config

  let tentativeNode: TentativeNode | null = null;

  let tentativeNodeMouseFollowerElement: HTMLElement | null = null;
  function moveTentativeNodeMouseFollower(e: MouseEvent) {
    if (!tentativeNodeMouseFollowerElement) return;
    tentativeNodeMouseFollowerElement.style.left = e.pageX + "px";
    tentativeNodeMouseFollowerElement.style.top = e.pageY + "px";
  }

  function nodeFactory(kind: NodeKind, typeKey: NodeTypeKey, configFactory: ConfigFactory) {
    return () => {
      const nodeId = generateNodeId(kind, typeKey);
      const config = configFactory(nodeId, $t, $languageConfigStore, ufConfig, $locale);
      tentativeNode = {
        kind,
        typeKey,
        id: nodeId,
        config,
      };
      console.debug(`Tentative node created`, tentativeNode);
    };
  }

  function customMouseDownHandler(e: MouseEvent, cursor: { x: number; y: number }): boolean {
    if (tentativeNode === null) return false;
    console.debug("Mouse-down event received with tentative node set, processing, cursor=", cursor);
    if (e.button == 2) {
      console.debug("RMB click, tentative node dropped");
      tentativeNode = null;
      return true;
    }
    ufConfig.node_display_coords[tentativeNode.id] = {
      x: cursor.x - 125, // half-width of the node in svelvet's coords
      y: cursor.y - 50, // just some arbitrary offset
    };
    if (tentativeNode.kind === NodeKind.block) {
      ufConfig.blocks = [...ufConfig.blocks, tentativeNode.config];
    } else {
      ufConfig.entrypoints = [...ufConfig.entrypoints, tentativeNode.config];
    }
    tentativeNode = null;
    return true;
  }

  function cloneNode(event: CustomEvent<string>) {
    const id = event.detail;
    const entrypointIdx = ufConfig.entrypoints.map(getEntrypointId).findIndex((eId) => eId === id);
    const blockIdx = ufConfig.blocks.map(getBlockId).findIndex((bId) => bId === id);
    if (entrypointIdx !== -1) {
      tentativeNode = cloneEntrypointConfig(ufConfig.entrypoints[entrypointIdx]);
    } else if (blockIdx !== -1) {
      tentativeNode = cloneBlockConfig(ufConfig.blocks[blockIdx]);
    } else {
      console.error(`Node with id '${id}' not found among entrypoints and blocks`);
      return;
    }
  }

  // region: node validation

  let isNodeValid: { [k: string]: boolean } = {};
  let configValidationResult: Result<null> = ok(null);
  $: {
    configValidationResult = ok(null);
    if (
      ufConfig.blocks.some((b) => !isNodeValid[getBlockId(b)]) ||
      ufConfig.entrypoints.some((e) => !isNodeValid[getEntrypointId(e)])
    ) {
      configValidationResult = err($t("studio.errors.config_validation_failed"));
    }
    const commandCounter = ufConfig.entrypoints
      .map((ep) => ep.command?.command)
      .filter((cmd) => cmd !== undefined)
      .reduce((acc: { [k: string]: number }, cmd) => {
        if (cmd) acc[cmd] = 1 + (acc[cmd] || 0);
        return acc;
      }, {});

    if (Object.values(commandCounter).some((v) => v > 1)) {
      configValidationResult = err($t("studio.errors.repeated_blocks"));
    }
    if (ufConfig.blocks.map((b) => b.language_select).filter((ls) => ls).length > 1) {
      configValidationResult = err($t("studio.errors.multiple_langselects"));
    }
  }

  // region: high-level actions

  let isSavingBotConfig = false;
  async function saveCurrentBotConfig(versionMessage: string | null, start: boolean) {
    if (readonly) return;
    if (!configValidationResult.ok) return;

    isSavingBotConfig = true;
    ufConfig.node_display_coords = filterNodeDisplayCoords(ufConfig.node_display_coords, ufConfig);
    const newBotConfig: BotConfig = {
      token_secret_name: botConfig.token_secret_name,
      user_flow_config: ufConfig,
      display_name: botConfig.display_name,
    };
    console.debug(`Saving bot config for ${botId}:`, newBotConfig);

    const res = await saveBotConfig(botId, { config: newBotConfig, version_message: versionMessage, start }, false);
    isSavingBotConfig = false;
    if (res.ok) {
      savedUfConfig = clone(ufConfig);
    } else {
      window.alert(`${$t("studio.errors.error_saving_bot_config")} ${res.error}`);
    }
  }

  const exitStudio = () => {
    deleteWorkingCopy();
    navigate(dashboardPath(botId));
  };
  const exitStudioWithConfirmation = withConfirmation(
    $t("studio.confirm_exit_unsaved_changes"),
    async () => exitStudio(),
    $t("studio.exit"),
  );

  const openReadmeModal = () =>
    open(ReadmeModal, { onShowcaseTemplate: () => applyTemplateToConfig(basicShowcaseTemplate()) }, INFO_MODAL_OPTIONS);
  if (localStorage.getItem(README_SHOWN_LS_KEY) === null) {
    localStorage.setItem(README_SHOWN_LS_KEY, "yea");
    openReadmeModal();
  }

  if (oldWorkingCopyUfConfigJson !== null) {
    const oldWorkingCopyUfConfig = JSON.parse(oldWorkingCopyUfConfigJson);
    if (!areEqual(oldWorkingCopyUfConfig, ufConfig)) {
      withConfirmation(
        $t("studio.draft_version_found"),
        async () => {
          ufConfig = JSON.parse(oldWorkingCopyUfConfigJson);
          forceRerender();
        },
        $t("studio.restore_draft"),
        $t("studio.delete_draft"),
      )();
    } else {
      console.debug("Found old working copy, but it's identical to the latest one");
    }
  }

  const applyTemplateToConfig = (template: Template) => {
    if (isMultilang && template.config.blocks.find((b) => b.language_select)) {
      alert($t("studio.errors.failed_to_add_template_langselect"));
      return;
    }
    console.debug("Applying template:", template);
    ufConfig = applyTemplate(ufConfig, template);
    isModified = true;
    forceRerender();
  };

  // region: markup
</script>

<svelte:window
  on:mousemove={moveTentativeNodeMouseFollower}
  on:keydown={(e) => {
    if (
      e.target &&
      // @ts-expect-error
      e.target.tagName !== "TEXTAREA" &&
      // @ts-expect-error
      e.target.tagName !== "INPUT" &&
      !e.repeat &&
      (e.metaKey || e.ctrlKey) &&
      e.code === "KeyZ"
    ) {
      undo();
    }
  }}
/>

<div class="svelvet-container">
  <div class="navbar-container">
    <Navbar>
      <div class="flex gap-2">
        <Heading tag="h3" class="mr-2 max-w-96 text-nowrap text-ellipsis overflow-clip" title={botConfig.display_name}>
          {botConfig.display_name}
        </Heading>
        {#if readonly || !configValidationResult.ok || !isModified}
          <Tooltip placement="bottom" triggeredBy="#save-button"
            >{readonly
              ? $t("studio.readonly_mode")
              : !configValidationResult.ok
                ? $t("studio.errors.validation_error") + getError(configValidationResult)
                : $t("studio.no_changes")}</Tooltip
          >
        {/if}
        <Button
          id="save-button"
          disabled={readonly || !configValidationResult.ok || !isModified || isSavingBotConfig}
          on:click={() => open(SaveConfigModal, { callback: saveCurrentBotConfig })}
        >
          {#if isSavingBotConfig}
            <Spinner class="me-3" size="4" color="white" />
          {/if}
          {$t("generic.save")}
        </Button>
        <Button outline on:click={isModified ? exitStudioWithConfirmation : exitStudio}>{$t("studio.exit")}</Button>
      </div>
    </Navbar>
  </div>
  {#key forceRerenderCounter}
    <!-- FIXME: add support for trackpad pan (just trackpadPan option breaks mouse compat) -->
    <Svelvet
      TD
      fitView
      edge={DeletableEdge}
      editable={false}
      minimap={false}
      enableAllHotkeys={false}
      controls
      {customMouseDownHandler}
      customCssCursor={tentativeNode ? "crosshair" : null}
    >
      <BotInfoNode {botId} bind:position={ufConfig.node_display_coords[BOT_INFO_NODE_ID]} />
      {#each ufConfig.entrypoints as entrypoint (getEntrypointId(entrypoint))}
        {#if entrypoint.command}
          <CommandEntryPointNode
            on:delete={deleteNode}
            bind:config={entrypoint.command}
            bind:position={ufConfig.node_display_coords[entrypoint.command.entrypoint_id]}
            bind:isValid={isNodeValid[entrypoint.command.entrypoint_id]}
          />
        {/if}
      {/each}
      {#each ufConfig.blocks as block (getBlockId(block))}
        {#if block.content}
          <ContentBlockNode
            {botId}
            on:delete={deleteNode}
            on:clone={cloneNode}
            bind:config={block.content}
            bind:position={ufConfig.node_display_coords[block.content.block_id]}
            bind:isValid={isNodeValid[block.content.block_id]}
          />
        {:else if block.human_operator}
          <HumanOperatorNode
            {botId}
            on:delete={deleteNode}
            on:clone={cloneNode}
            bind:config={block.human_operator}
            bind:position={ufConfig.node_display_coords[block.human_operator.block_id]}
            bind:isValid={isNodeValid[block.human_operator.block_id]}
          />
        {:else if block.language_select}
          <LanguageSelectNode
            on:delete={(e) => {
              deleteNode(e);
              languageConfigStore.set(null);
            }}
            bind:config={block.language_select}
            bind:position={ufConfig.node_display_coords[block.language_select.block_id]}
            bind:isValid={isNodeValid[block.language_select.block_id]}
          />
        {:else if block.menu}
          <MenuNode
            on:delete={deleteNode}
            on:clone={cloneNode}
            bind:config={block.menu}
            bind:position={ufConfig.node_display_coords[block.menu.block_id]}
            bind:isValid={isNodeValid[block.menu.block_id]}
          />
        {:else if block.form}
          <FormNode
            {botId}
            on:delete={deleteNode}
            on:clone={cloneNode}
            bind:config={block.form}
            bind:position={ufConfig.node_display_coords[block.form.block_id]}
            bind:isValid={isNodeValid[block.form.block_id]}
          />
        {/if}
      {/each}
    </Svelvet>
  {/key}
  <StudioSidePandel>
    <div>
      <div class="flex flex-col gap-2">
        <AddNodeButton
          key={NodeTypeKey.command}
          on:click={nodeFactory(NodeKind.entrypoint, NodeTypeKey.command, defaultCommandEntrypoint)}
        />
        <AddNodeButton
          key={NodeTypeKey.content}
          on:click={nodeFactory(NodeKind.block, NodeTypeKey.content, defaultContentBlockConfig)}
        />
        <AddNodeButton
          key={NodeTypeKey.menu}
          on:click={nodeFactory(NodeKind.block, NodeTypeKey.menu, defaultMenuBlockConfig)}
        />
        <AddNodeButton
          key={NodeTypeKey.human_operator}
          on:click={nodeFactory(NodeKind.block, NodeTypeKey.human_operator, defaultHumanOperatorBlockConfig)}
        />
        <AddNodeButton
          key={NodeTypeKey.form}
          on:click={nodeFactory(NodeKind.block, NodeTypeKey.form, defaultFormBlockConfig)}
        />
        <AddNodeButton
          key={NodeTypeKey.language_select}
          disabled={isMultilang}
          on:click={nodeFactory(NodeKind.block, NodeTypeKey.language_select, defaultLanguageSelectBlockConfig)}
        />
      </div>

      <div class="flex flex-col gap-2 pt-3 mt-3 border-t border-gray-200">
        <button
          on:click={() =>
            open(
              TemplatesModal,
              {
                templateSelectedCallback: applyTemplateToConfig,
              },
              INFO_MODAL_OPTIONS,
            )}
          class="border border-gray-500 flex flex-row items-center justify-start p-0 rounded-lg w-auto"
        >
          <div class="w-10 h-10 flex justify-center items-center border-r border-r-gray-500">
            <GridPlusColored
              class="w-7 h-7"
              colors={[
                headerColor(NODE_HUE[NodeTypeKey.command]),
                headerColor(NODE_HUE[NodeTypeKey.language_select]),
                headerColor(NODE_HUE[NodeTypeKey.menu]),
              ]}
            />
          </div>
          <span class="px-3">{$t("studio.open_templates")}</span>
        </button>

        <button
          on:click={openReadmeModal}
          class="border border-gray-500 flex flex-row items-center justify-start p-0 rounded-lg w-auto"
        >
          <div class="w-10 h-10 flex justify-center items-center border-r border-r-gray-500">
            <QuestionCircleOutline class="w-5 h-5" />
          </div>
          <span class="px-3">{$t("studio.open_readme")}</span>
        </button>
      </div>
    </div>
  </StudioSidePandel>
  {#if tentativeNode}
    <div
      id="tentative-node-mouse-follower"
      style="background-color: {headerColor(NODE_HUE[tentativeNode.typeKey])}"
      bind:this={tentativeNodeMouseFollowerElement}
    >
      <div class="flex items-center gap-2">
        <svelte:component this={NODE_ICON[tentativeNode.typeKey]} class="w-4 h-4" />
        <span class="font-bold text-lg">{$t(NODE_TITLE_KEY[tentativeNode.typeKey])}</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .svelvet-container {
    width: 100%;
    height: 100vh;
  }
  div.navbar-container {
    position: absolute;
    top: 0;
    z-index: 100;
    width: 100%;
  }
  #tentative-node-mouse-follower {
    opacity: 0.8;
    position: absolute;
    top: -300px;
    left: -300px;
    /* x, y of cursor should be above in the center */
    transform: translate(-50%, -140%);
    /* mimicking node styles */
    background-color: white;
    border-radius: 0;
    border: solid 1px rgb(206, 212, 218);
    padding: 8px;
  }
</style>
