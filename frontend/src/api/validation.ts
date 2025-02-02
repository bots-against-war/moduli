import { toDataResult, type Result } from "../utils";
import type { BotTokenValidationResult } from "./types";
import { fetchApi } from "./utils";

export async function validateBotToken(token: string): Promise<Result<BotTokenValidationResult, string>> {
  const res = await fetchApi("/validate-token", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
  return toDataResult(res);
}
