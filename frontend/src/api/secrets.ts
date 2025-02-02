import { toDataResult, toTrivialResult, type Result } from "../utils";
import { fetchApi } from "./utils";

export async function listSecrets(): Promise<Result<string[], string>> {
  const res = await fetchApi(`/secrets`);
  return await toDataResult(res);
}

export async function saveTokenSecret(name: string, value: string): Promise<Result<null>> {
  const res = await fetchApi(`/secrets/${encodeURIComponent(name)}?is_token=true`, {
    method: "POST",
    body: value,
  });
  return await toTrivialResult(res);
}

export async function deleteSecret(name: string): Promise<Result<null>> {
  const res = await fetchApi(`/secrets/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  return await toTrivialResult(res);
}
