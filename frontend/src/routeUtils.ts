export function formResultsPagePath(botId: string, formBlockId: string): string {
  return `/forms/${encodeURIComponent(botId)}/${encodeURIComponent(formBlockId)}`;
}

export function studioPath(botId: string, version: number | null): string {
  let path = `/studio/${encodeURIComponent(botId)}`;
  if (version !== null) {
    path += `?version=${encodeURIComponent(version)}`;
  }
  return path;
}

export function dashboardPath(botId: string | null): string {
  if (botId) {
    return `/#${botId}`;
  } else {
    return "/";
  }
}