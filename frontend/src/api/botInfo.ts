import { toDataResult, toTrivialResult, type Result } from "../utils";
import type { BotInfo, BotVersionsPage } from "./types";
import { fetchApi, paginationQuery } from "./utils";

export async function getBotInfo(botId: string): Promise<Result<BotInfo>> {
  const res = await fetchApi(`/info/${encodeURIComponent(botId)}`);
  return await toDataResult(res);
}

export async function getBotInfoShort(botId: string): Promise<Result<BotInfo>> {
  const res = await fetchApi(`/info/${encodeURIComponent(botId)}?detailed=false`);
  return await toDataResult(res);
}

export async function listBotInfos(allForRoot: boolean): Promise<Result<BotInfo[]>> {
  const res = await fetchApi(`/info?detailed=false&all=${allForRoot ? "true" : "false"}`);
  return await toDataResult(res);
}

export async function updateBotDisplayName(botId: string, newDisplayName: string): Promise<Result<null>> {
  const res = await fetchApi(`/display-name/${botId}`, {
    method: "PUT",
    body: JSON.stringify({ display_name: newDisplayName }),
  });
  return await toTrivialResult(res);
}

export async function getBotVersionsPage(
  botId: string,
  offset: number,
  count: number,
): Promise<Result<BotVersionsPage>> {
  const res = await fetchApi(`/info/${encodeURIComponent(botId)}/versions?${paginationQuery(offset, count)}`);
  return await toDataResult(res);
}
