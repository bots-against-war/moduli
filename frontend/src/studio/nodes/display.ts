import {
  ClipboardSolid,
  CodeForkSolid,
  CodeOutline,
  GlobeSolid,
  InfoCircleSolid,
  NewspaperSolid,
  UserHeadsetSolid,
} from "flowbite-svelte-icons";
import { SvelteComponent } from "svelte";
import type { Newable } from "ts-essentials";
import type { UserFlowBlockConfig, UserFlowEntryPointConfig } from "../../api/types";

export enum NodeTypeKey {
  command = "command",
  content = "content",
  human_operator = "human_operator",
  language_select = "language_select",
  menu = "menu",
  form = "form",
  info = "info",
}

export function getNodeTypeKey(config: UserFlowBlockConfig | UserFlowEntryPointConfig): NodeTypeKey | null {
  if (config.command) {
    return NodeTypeKey.command;
  } else if (config.content) {
    return NodeTypeKey.content;
  } else if (config.human_operator) {
    return NodeTypeKey.human_operator;
  } else if (config.language_select) {
    return NodeTypeKey.language_select;
  } else if (config.menu) {
    return NodeTypeKey.menu;
  } else if (config.form) {
    return NodeTypeKey.form;
  } else {
    return null;
  }
}

export const NODE_HUE: { [key in NodeTypeKey]: number | "white" } = {
  command: 270.5,
  content: 26,
  human_operator: 330,
  language_select: 195.5,
  menu: 80,
  form: 48,
  info: "white", // = white
};

export function headerColor(hue: number | "white"): string {
  if (hue === "white") return "hsl(0, 0%, 90%)";
  return `hsl(${hue}, 70%, 70%)`;
}

export const NODE_TITLE_KEY: { [key in NodeTypeKey]: string } = {
  command: "studio.node_titles.command",
  content: "studio.node_titles.content",
  human_operator: "studio.node_titles.human_operator",
  language_select: "studio.node_titles.language_select",
  menu: "studio.node_titles.menu",
  form: "studio.node_titles.form",
  info: "studio.node_titles.bot_info",
};

export const NODE_ICON: { [key in NodeTypeKey]: Newable<SvelteComponent> } = {
  command: CodeOutline,
  content: NewspaperSolid,
  human_operator: UserHeadsetSolid,
  language_select: GlobeSolid,
  menu: CodeForkSolid,
  form: ClipboardSolid,
  info: InfoCircleSolid,
};
