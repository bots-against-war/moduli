import { toTrivialResult, type Result } from "../utils";
import { fetchApi } from "./utils";

export async function validateBotToken(token: string): Promise<Result<null, string>> {
  const res = await fetchApi("/validate-token?must_be_unused=true", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
  return await toTrivialResult(res);
}
