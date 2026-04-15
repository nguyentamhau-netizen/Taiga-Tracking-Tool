export type ItemKind = "userstory" | "task" | "issue";

export type UserOption = {
  id: number;
  full_name: string;
  username?: string | null;
  role_name?: string | null;
  role_group?: string | null;
};

export type SprintOption = {
  id: number;
  name: string;
  estimated_start?: string | null;
  estimated_finish?: string | null;
  closed: boolean;
};

export type StatusOption = {
  id: number;
  name: string;
  color?: string | null;
};

export type TrackerItem = {
  kind: ItemKind;
  id: number;
  ref?: number | null;
  subject: string;
  status_id?: number | null;
  status_name: string;
  status_color?: string | null;
  assignees: UserOption[];
  watchers: UserOption[];
  sprint_id?: number | null;
  sprint_name?: string | null;
  is_no_sprint: boolean;
  updated_at?: string | null;
  created_at?: string | null;
  due_date?: string | null;
  tags: string[];
  severity?: string | null;
  priority?: string | null;
  url?: string | null;
};

export type MetadataResponse = {
  project_name: string;
  auto_refresh_minutes: number;
  qc_names: string[];
  me: {
    id: number;
    full_name: string;
    email?: string | null;
    username?: string | null;
  };
  sprints: SprintOption[];
  statuses: Record<ItemKind, StatusOption[]>;
  users: UserOption[];
};

export type ItemsResponse = {
  items: TrackerItem[];
};

export type ItemUpdateResponse = {
  ok: boolean;
  item: TrackerItem;
};

const API_ROOT = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ ok: boolean }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  me: () => request<{ ok: boolean; user: MetadataResponse["me"] }>("/auth/me"),
  metadata: () => request<MetadataResponse>("/metadata"),
  sync: () => request<{ ok: boolean }>("/sync", { method: "POST" }),
  items: (params: {
    kind?: ItemKind | "all";
    sprintIds?: number[];
    statuses?: string[];
    assigneeIds?: number[];
    search?: string;
    noSprintOnly?: boolean;
    notAssignedQcOnly?: boolean;
    assignedToMeOnly?: boolean;
  }) => {
    const query = new URLSearchParams();
    if (params.kind) query.set("kind", params.kind);
    if (params.sprintIds?.length) query.set("sprint_ids", params.sprintIds.join(","));
    if (params.statuses?.length) query.set("statuses", params.statuses.join(","));
    if (params.assigneeIds?.length) query.set("assignee_ids", params.assigneeIds.join(","));
    if (params.search?.trim()) query.set("search", params.search.trim());
    if (params.noSprintOnly) query.set("no_sprint_only", "true");
    if (params.notAssignedQcOnly) query.set("not_assigned_qc_only", "true");
    if (params.assignedToMeOnly) query.set("assigned_to_me_only", "true");
    return request<ItemsResponse>(`/items?${query.toString()}`);
  },
  updateItem: (
    kind: ItemKind,
    itemId: number,
    payload: {
      status_id?: number | null;
      assignee_ids?: number[] | null;
      watcher_ids?: number[] | null;
      sprint_id?: number | null;
      comment?: string | null;
    },
  ) =>
    request<ItemUpdateResponse>(`/items/${kind}/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
