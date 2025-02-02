import { getContext, type ComponentProps, type SvelteComponent } from "svelte";
import type { Newable } from "ts-essentials";
import { saveTokenSecret } from "./api/secrets";
import ConfirmationModal from "./components/ConfirmationModal.svelte";

// rust-like result type with convenience functions

export type Result<T, E = string> = { data: T; ok: true } | { error: E; ok: false };

export function ok<T, E = string>(data: T): Result<T, E> {
  return { data, ok: true };
}

export function err<T, E = string>(error: E): Result<T, E> {
  return { error, ok: false };
}

export function unwrap<T, E = string>(result: Result<T, E>): T {
  if (result.ok) {
    return result.data;
  } else {
    // @ts-expect-error
    throw new Error(result.error);
  }
}

export function convert<T1, T2, E>(r: Result<T1, E>, converter: (from: T1) => T2): Result<T2, E> {
  if (r.ok) {
    return ok(converter(r.data));
  } else {
    return r;
  }
}

export function getError<E = string>(result: Result<any, E>): E | null {
  if (result.ok) {
    return null;
  } else {
    // @ts-ignore
    return result.error;
  }
}

export async function toTrivialResult(res: Result<Response>): Promise<Result<null, string>> {
  if (!res.ok) return res;
  const response = res.data;
  if (response.ok) {
    return ok(null);
  } else {
    return err(await response.text());
  }
}

export async function toDataResult<T>(res: Result<Response>): Promise<Result<T, string>> {
  if (!res.ok) return res;
  const response = res.data;
  const responseText = await response.text();
  if (response.ok) return ok(JSON.parse(responseText));
  else return err(responseText);
}

export async function toStringResult(res: Result<Response>): Promise<Result<string, string>> {
  if (!res.ok) return res;
  const response = res.data;
  const responseText = await response.text();
  if (response.ok) return ok(responseText);
  else return err(responseText);
}

export function mean(data: number[]): number {
  if (data.length < 1) {
    return NaN;
  }
  return data.reduce((prev, current) => prev + current) / data.length;
}

// typed version of svelte-simple-modals open func
export function getModalOpener<C extends SvelteComponent>(): (
  modalCompClass: Newable<C>,
  props?: ComponentProps<C>,
  options?: any,
) => void {
  // @ts-expect-error
  const { open } = getContext("simple-modal");
  return open;
}

// typed version of svelte-simple-modals close func
export function getModalCloser(): () => void {
  // @ts-expect-error
  const { close } = getContext("simple-modal");
  return close;
}

export const INFO_MODAL_OPTIONS = {
  closeButton: true,
  closeOnEsc: true,
  closeOnOuterClick: true,
};

export async function createBotTokenSecret(botId: string, token: string): Promise<Result<string, string>> {
  let secretName = botId + "-token-" + crypto.randomUUID().slice(0, 8);
  console.debug("Generated secret name", secretName);
  let res = await saveTokenSecret(secretName, token);
  let saveSecretError = getError(res);
  if (saveSecretError !== null) {
    return err(saveSecretError);
  } else {
    return ok(secretName);
  }
}

// NOTE: this function must be called on component initialization!
export function withConfirmation(
  text: string,
  onConfirm: () => Promise<any>,
  confirmButtonLabel: string,
  cancelButtonLabel: string | null = null,
) {
  const open = getModalOpener();
  return () => {
    open(ConfirmationModal, {
      text,
      onConfirm,
      confirmButtonLabel,
      cancelButtonLabel,
    });
  };
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function truncateText(s: string, len: number): [string, boolean] {
  if (s.length <= len) {
    return [s, false];
  } else {
    return [s.substring(0, len) + "...", true];
  }
}
