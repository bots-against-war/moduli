import { toDataResult, type Result } from "../utils";
import type { BotConfig, SaveBotConfigVersionPayload } from "./types";
import { fetchApi } from "./utils";

export async function saveBotConfig(
  botId: string,
  payload: SaveBotConfigVersionPayload,
  new_: boolean,
): Promise<Result<BotConfig>> {
  const res = await fetchApi(`/config/${encodeURIComponent(botId)}?new=${new_ ? "true" : "false"}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return await toDataResult(res);
}

export async function loadBotConfig(botId: string, version: number | null): Promise<Result<BotConfig>> {
  let path = `/config/${encodeURIComponent(botId)}?with_display_name=1`;
  if (version !== null) {
    path = path + `&version=${encodeURIComponent(version)}`;
  }
  const res = await fetchApi(path);
  return await toDataResult(res);
}

export async function deleteBotConfig(botId: string): Promise<Result<BotConfig>> {
  const res = await fetchApi(`/config/${encodeURIComponent(botId)}`, { method: "DELETE" });
  return await toDataResult(res);
}
