export const BASE_PATH = import.meta.env.BASE_URL;

function withBasePath(path: string): string {
  const prefix = BASE_PATH === "/" ? "" : BASE_PATH;
  return prefix + path;
}

function encodePathPart(part: any): any {
  if (typeof part !== "string") {
    return part;
  }
  // :identifier is a syntax used to render templates for svelte-simple-routing
  return part.at(0) === ":" ? part : encodeURIComponent(part);
}

export function formResultsPagePath(botId: string, formBlockId: string): string {
  return withBasePath(`/forms/${encodePathPart(botId)}/${encodePathPart(formBlockId)}`);
}

export function studioPath(botId: string, version: number | null): string {
  let relpath = `/studio/${encodePathPart(botId)}`;
  if (version !== null) {
    relpath += `?version=${encodePathPart(version)}`;
  }
  return withBasePath(relpath);
}

export function dashboardPath(botId: string): string {
  return withBasePath(`/dashboard/${encodePathPart(botId)}`);
}

export function botListingPath(): string {
  return withBasePath("/bots");
}

export function versionsPagePath(botId: string): string {
  return withBasePath(`/versions/${encodePathPart(botId)}`);
}

export function settingsPath(botId: string): string {
  return withBasePath(`/settings/${encodePathPart(botId)}`);
}

export function errorsPath(botId: string): string {
  return withBasePath(`/errors/${encodePathPart(botId)}`);
}

export function landingPath(): string {
  return withBasePath("");
}
