import { useEffect, useMemo, useRef, useState } from "react";
import * as XLSX from "xlsx";
import { api, ItemKind, MetadataResponse, TrackerItem } from "./lib/api";

type TabKey = "userstory" | "task" | "issue";
type FilterState = {
  sprintIds: number[];
  statuses: string[];
  assigneeIds: number[];
  search: string;
  noSprintOnly: boolean;
  notAssignedQcOnly: boolean;
  assignedToMeOnly: boolean;
};
type EditDraft = {
  statusId: number | "";
  sprintId: number | "";
  assigneeIds: number[];
  watcherIds: number[];
  comment: string;
};

function formatUsers(users: TrackerItem["assignees"]) {
  return users.map((user) => user.full_name).join(", ");
}

function formatUsersByRole(users: TrackerItem["assignees"], roleGroup: "PO" | "DEV" | "QC") {
  return users.filter((user) => user.role_group === roleGroup).map((user) => user.full_name).join(", ");
}

function MultiSelectDropdown<T extends string | number>({
  label,
  options,
  selectedValues,
  onToggle,
  onRemove,
  compact = false,
  placeholder,
}: {
  label: string;
  options: { value: T; label: string }[];
  selectedValues: T[];
  onToggle: (value: T) => void;
  onRemove: (value: T) => void;
  compact?: boolean;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const dropdownIdRef = useRef(`dropdown-${label.replace(/\s+/g, "-").toLowerCase()}`);
  const selectedOptions = options.filter((option) => selectedValues.includes(option.value));
  const filteredOptions = useMemo(
    () => options.filter((option) => option.label.toLowerCase().includes(query.trim().toLowerCase())),
    [options, query],
  );

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [open]);

  useEffect(() => {
    const handleDropdownOpen = (event: Event) => {
      const customEvent = event as CustomEvent<string>;
      if (customEvent.detail !== dropdownIdRef.current) {
        setOpen(false);
      }
    };

    window.addEventListener("taiga-filter-open", handleDropdownOpen as EventListener);
    return () => window.removeEventListener("taiga-filter-open", handleDropdownOpen as EventListener);
  }, []);

  return (
    <div className={`multi-dropdown ${compact ? "compact" : ""}`} ref={containerRef}>
      {compact ? null : <span className="multi-filter-label">{label}</span>}
      <div
        className="multi-dropdown-trigger"
        onClick={() =>
          setOpen((current) => {
            const nextOpen = !current;
            if (nextOpen) {
              window.dispatchEvent(new CustomEvent("taiga-filter-open", { detail: dropdownIdRef.current }));
            }
            return nextOpen;
          })
        }
        role="button"
        tabIndex={0}
      >
        {selectedOptions.length ? (
          <div className="multi-dropdown-chips">
            {selectedOptions.map((option) => (
              <button
                key={String(option.value)}
                type="button"
                className="multi-dropdown-chip"
                onClick={(event) => {
                  event.stopPropagation();
                  onRemove(option.value);
                }}
              >
                {option.label} x
              </button>
            ))}
          </div>
        ) : (
          <span className="multi-dropdown-placeholder">{placeholder ?? `Select ${label.toLowerCase()}`}</span>
        )}
      </div>
      {open ? (
        <div className="multi-dropdown-panel">
          <input
            className="multi-dropdown-search"
            placeholder={`Search ${label.toLowerCase()}`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="multi-filter-list">
            {filteredOptions.map((option) => (
              <button
                key={String(option.value)}
                type="button"
                className={`multi-filter-item ${selectedValues.includes(option.value) ? "selected" : ""}`}
                onClick={() => onToggle(option.value)}
              >
                <span className="multi-filter-text">{option.label}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SummaryBar({
  items,
  onApplySummaryFilter,
}: {
  items: TrackerItem[];
  onApplySummaryFilter: (kind: "all" | "noSprint" | "missingQc") => void;
}) {
  const noSprintCount = items.filter((item) => item.is_no_sprint).length;
  const missingQcCount = items.filter((item) => item.assignees.length === 0 && item.watchers.length === 0).length;
  const assignedCount = items.length;

  return (
    <div className="summary-row">
      <button className="summary-card" onClick={() => onApplySummaryFilter("all")}>
        <strong>{assignedCount}</strong>
        <span>Current Results</span>
      </button>
      <button className="summary-card" onClick={() => onApplySummaryFilter("noSprint")}>
        <strong>{noSprintCount}</strong>
        <span>No Sprint</span>
      </button>
      <button className="summary-card" onClick={() => onApplySummaryFilter("missingQc")}>
        <strong>{missingQcCount}</strong>
        <span>No QC Assigned</span>
      </button>
    </div>
  );
}

function exportItems(items: TrackerItem[], fileName: string) {
  const rows = items.map((item) => ({
    Type: item.kind,
    Ref: item.ref ?? "",
    Subject: item.subject,
    Status: item.status_name,
    Sprint: item.sprint_name ?? "",
    Assignees: formatUsers(item.assignees),
    Watchers: formatUsers(item.watchers),
    UpdatedAt: item.updated_at ?? "",
    CreatedAt: item.created_at ?? "",
    Url: item.url ?? "",
  }));
  const workbook = XLSX.utils.book_new();
  const worksheet = XLSX.utils.json_to_sheet(rows);
  XLSX.utils.book_append_sheet(workbook, worksheet, "Items");
  XLSX.writeFile(workbook, fileName);
}

function SelectedFilters({
  metadata,
  filters,
  onRemoveSprint,
  onRemoveStatus,
  onRemoveAssignee,
  onClearSearch,
  onToggleNoSprint,
  onToggleNotAssignedQc,
  onToggleAssignedToMe,
}: {
  metadata: MetadataResponse;
  filters: FilterState;
  onRemoveSprint: (id: number) => void;
  onRemoveStatus: (value: string) => void;
  onRemoveAssignee: (id: number) => void;
  onClearSearch: () => void;
  onToggleNoSprint: () => void;
  onToggleNotAssignedQc: () => void;
  onToggleAssignedToMe: () => void;
}) {
  const chips: { key: string; label: string; onClick: () => void }[] = [];
  const sprintMap = new Map(metadata.sprints.map((sprint) => [sprint.id, sprint.name]));
  const assigneeMap = new Map(metadata.users.map((user) => [user.id, user.full_name]));
  filters.sprintIds.forEach((id) => chips.push({ key: `s-${id}`, label: `Sprint: ${sprintMap.get(id) ?? id}`, onClick: () => onRemoveSprint(id) }));
  filters.statuses.forEach((status) => chips.push({ key: `st-${status}`, label: `Status: ${status}`, onClick: () => onRemoveStatus(status) }));
  filters.assigneeIds.forEach((id) => chips.push({ key: `a-${id}`, label: `QC: ${assigneeMap.get(id) ?? id}`, onClick: () => onRemoveAssignee(id) }));
  if (filters.noSprintOnly) chips.push({ key: "no-sprint", label: "No Sprint", onClick: onToggleNoSprint });
  if (filters.notAssignedQcOnly) chips.push({ key: "not-qc", label: "Not Assigned QC", onClick: onToggleNotAssignedQc });
  if (filters.assignedToMeOnly) chips.push({ key: "me", label: "Assigned To Me", onClick: onToggleAssignedToMe });
  if (filters.search.trim()) chips.push({ key: "search", label: `Search: ${filters.search.trim()}`, onClick: onClearSearch });
  if (!chips.length) return null;

  return (
    <div className="chip-row">
      {chips.map((chip) => (
        <button key={chip.key} className="chip" onClick={chip.onClick}>
          {chip.label} x
        </button>
      ))}
    </div>
  );
}

function ItemTable({
  metadata,
  items,
  currentKind,
  title,
  loading,
  saving,
  editingItemId,
  draft,
  onRefresh,
  onExport,
  onStartEdit,
  onCancelEdit,
  onDraftChange,
  onSaveEdit,
}: {
  metadata: MetadataResponse;
  items: TrackerItem[];
  currentKind: ItemKind;
  title: string;
  loading: boolean;
  saving: boolean;
  editingItemId: number | null;
  draft: EditDraft | null;
  onRefresh: () => void;
  onExport: () => void;
  onStartEdit: (item: TrackerItem) => void;
  onCancelEdit: () => void;
  onDraftChange: (draft: EditDraft) => void;
  onSaveEdit: (item: TrackerItem) => void;
}) {
  const statusOptions = metadata.statuses[currentKind] ?? [];

  return (
    <div className="table-wrap">
      <div className="table-header">
        <h3>{title}</h3>
        <div className="actions">
          <button onClick={onRefresh}>Refresh</button>
          <button onClick={onExport}>Export</button>
        </div>
      </div>
      {loading ? <p>Loading...</p> : null}
      <table>
        <thead>
          <tr>
            <th>Ref</th>
            <th>Subject</th>
            <th>Status</th>
            <th>Sprint</th>
            <th>PO</th>
            <th>DEV</th>
            <th>QC</th>
            <th>Watchers</th>
            <th>Comment</th>
            <th>Updated</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const isEditing = editingItemId === item.id && draft;
            return (
              <tr key={`${item.kind}-${item.id}`} className={isEditing ? "editor-row" : ""}>
                <td>{item.ref ?? item.id}</td>
                <td>{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.subject}</a> : item.subject}</td>
                <td>
                  {isEditing ? (
                    <select
                      value={draft.statusId === "" ? "" : String(draft.statusId)}
                      onChange={(event) => onDraftChange({ ...draft, statusId: event.target.value ? Number(event.target.value) : "" })}
                    >
                      <option value="">Keep current</option>
                      {statusOptions.map((status) => <option key={status.id} value={status.id}>{status.name}</option>)}
                    </select>
                  ) : (
                    item.status_name
                  )}
                </td>
                <td>
                  {isEditing ? (
                    <select
                      value={draft.sprintId === "" ? "" : String(draft.sprintId)}
                      onChange={(event) => onDraftChange({ ...draft, sprintId: event.target.value ? Number(event.target.value) : "" })}
                    >
                      <option value="">No sprint</option>
                      {metadata.sprints.map((sprint) => <option key={sprint.id} value={sprint.id}>{sprint.name}</option>)}
                    </select>
                  ) : (
                    item.sprint_name ?? "No sprint"
                  )}
                </td>
                <td>{formatUsersByRole(item.assignees, "PO")}</td>
                <td>{formatUsersByRole(item.assignees, "DEV")}</td>
                <td>
                  {isEditing ? (
                    <MultiSelectDropdown
                      label="QC Assignees"
                      compact
                      placeholder="Select QC assignees"
                      options={metadata.users.map((user) => ({ value: user.id, label: user.full_name }))}
                      selectedValues={draft.assigneeIds}
                      onRemove={(value) => onDraftChange({ ...draft, assigneeIds: draft.assigneeIds.filter((item) => item !== value) })}
                      onToggle={(value) =>
                        onDraftChange({
                          ...draft,
                          assigneeIds: draft.assigneeIds.includes(value)
                            ? draft.assigneeIds.filter((item) => item !== value)
                            : [...draft.assigneeIds, value],
                        })
                      }
                    />
                  ) : (
                    formatUsersByRole(item.assignees, "QC")
                  )}
                </td>
                <td>
                  {isEditing ? (
                    <MultiSelectDropdown
                      label="QC Watchers"
                      compact
                      placeholder="Select QC watchers"
                      options={metadata.users.map((user) => ({ value: user.id, label: user.full_name }))}
                      selectedValues={draft.watcherIds}
                      onRemove={(value) => onDraftChange({ ...draft, watcherIds: draft.watcherIds.filter((item) => item !== value) })}
                      onToggle={(value) =>
                        onDraftChange({
                          ...draft,
                          watcherIds: draft.watcherIds.includes(value)
                            ? draft.watcherIds.filter((item) => item !== value)
                            : [...draft.watcherIds, value],
                        })
                      }
                    />
                  ) : (
                    formatUsers(item.watchers)
                  )}
                </td>
                <td>
                  {isEditing ? (
                    <textarea
                      className="inline-comment"
                      value={draft.comment}
                      onChange={(event) => onDraftChange({ ...draft, comment: event.target.value })}
                      placeholder="Add comment to Taiga"
                      rows={3}
                    />
                  ) : (
                    ""
                  )}
                </td>
                <td>{item.updated_at ? new Date(item.updated_at).toLocaleString() : ""}</td>
                <td>
                  {isEditing ? (
                    <div className="inline-actions">
                      <button onClick={() => onSaveEdit(item)} disabled={saving}>{saving ? "Saving..." : "Save"}</button>
                      <button onClick={onCancelEdit} disabled={saving}>Cancel</button>
                    </div>
                  ) : (
                    <button onClick={() => onStartEdit(item)}>Edit</button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function App() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loggedIn, setLoggedIn] = useState(false);
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null);
  const [items, setItems] = useState<TrackerItem[]>([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [savingItem, setSavingItem] = useState<number | null>(null);
  const [tab, setTab] = useState<TabKey>("userstory");
  const [editingItemId, setEditingItemId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    sprintIds: [],
    statuses: [],
    assigneeIds: [],
    search: "",
    noSprintOnly: false,
    notAssignedQcOnly: false,
    assignedToMeOnly: false,
  });
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });

  const hasActiveFilters =
    filters.sprintIds.length > 0 ||
    filters.statuses.length > 0 ||
    filters.assigneeIds.length > 0 ||
    filters.search.trim().length > 0 ||
    filters.noSprintOnly ||
    filters.notAssignedQcOnly ||
    filters.assignedToMeOnly;

  const loadMetadata = async () => {
    const response = await api.metadata();
    setMetadata(response);
    setLoggedIn(true);
    return response;
  };

  const loadItems = async () => {
    if (!hasActiveFilters) {
      setItems([]);
      setItemsLoading(false);
      return;
    }
    setItemsLoading(true);
    try {
      const response = await api.items({
        kind: tab as ItemKind,
        sprintIds: filters.sprintIds,
        statuses: filters.statuses,
        assigneeIds: filters.assigneeIds,
        search: filters.search,
        noSprintOnly: filters.noSprintOnly,
        notAssignedQcOnly: filters.notAssignedQcOnly,
        assignedToMeOnly: filters.assignedToMeOnly,
      });
      setItems(response.items);
    } finally {
      setItemsLoading(false);
    }
  };

  useEffect(() => {
    api.me().then(() => loadMetadata()).catch(() => setLoading(false)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setEditingItemId(null);
    setEditDraft(null);
  }, [tab]);

  useEffect(() => {
    if (!metadata) return;
    if (!hasActiveFilters) {
      setItems([]);
      return;
    }
    void loadItems();
  }, [metadata, tab, hasActiveFilters, filters.sprintIds, filters.statuses, filters.assigneeIds, filters.search, filters.noSprintOnly, filters.notAssignedQcOnly, filters.assignedToMeOnly]);

  useEffect(() => {
    if (!metadata || !hasActiveFilters) return;
    const timer = window.setInterval(() => {
      void loadItems();
    }, metadata.auto_refresh_minutes * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [metadata, tab, hasActiveFilters, filters.sprintIds, filters.statuses, filters.assigneeIds, filters.search, filters.noSprintOnly, filters.notAssignedQcOnly, filters.assignedToMeOnly]);

  const handleLogin = async () => {
    setLoading(true);
    setError("");
    try {
      await api.login(loginForm.username, loginForm.password);
      await loadMetadata();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setError("");
    try {
      await api.sync();
      await loadMetadata();
      if (hasActiveFilters) {
        await loadItems();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSyncing(false);
    }
  };

  const handleStartEdit = (item: TrackerItem) => {
    setEditingItemId(item.id);
    setEditDraft({
      statusId: item.status_id ?? "",
      sprintId: item.sprint_id ?? "",
      assigneeIds: item.assignees.filter((user) => user.role_group === "QC").map((user) => user.id),
      watcherIds: item.watchers.filter((user) => user.role_group === "QC" || !user.role_group).map((user) => user.id),
      comment: "",
    });
  };

  const handleSaveEdit = async (item: TrackerItem) => {
    if (!editDraft) return;
    setSavingItem(item.id);
    setError("");
    try {
      const nonQcAssigneeIds = item.assignees.filter((user) => user.role_group !== "QC").map((user) => user.id);
      const nonQcWatcherIds = item.watchers.filter((user) => user.role_group !== "QC").map((user) => user.id);
      const response = await api.updateItem(item.kind, item.id, {
        status_id: editDraft.statusId === "" ? item.status_id ?? null : editDraft.statusId,
        sprint_id: editDraft.sprintId === "" ? null : editDraft.sprintId,
        assignee_ids: [...new Set([...nonQcAssigneeIds, ...editDraft.assigneeIds])],
        watcher_ids: [...new Set([...nonQcWatcherIds, ...editDraft.watcherIds])],
        comment: editDraft.comment.trim() || null,
      });
      setEditingItemId(null);
      setEditDraft(null);
      setItems((current) => current.map((row) => (row.kind === item.kind && row.id === item.id ? response.item : row)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingItem(null);
    }
  };

  if (!loggedIn) {
    return (
      <main className="shell">
        <section className="login-card" onKeyDown={(event) => { if (event.key === "Enter") void handleLogin(); }}>
          <h1>Taiga QC Tracker</h1>
          <p>Sign in with your Taiga account.</p>
          <input placeholder="Email or username" value={loginForm.username} onChange={(event) => setLoginForm((current) => ({ ...current, username: event.target.value }))} />
          <input type="password" placeholder="Password" value={loginForm.password} onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))} />
          <button onClick={() => void handleLogin()} disabled={loading}>{loading ? "Signing in..." : "Sign in"}</button>
          {error ? <pre className="error-box">{error}</pre> : null}
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <h1>Taiga QC Tracker</h1>
          <p>{metadata?.project_name}</p>
        </div>
        <div className="actions">
          <input className="search" placeholder="Search current tab" value={filters.search} onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))} />
          <button onClick={() => void loadItems()}>Refresh</button>
          <button onClick={() => void handleSync()} disabled={syncing}>{syncing ? "Refreshing Taiga..." : "Refresh from Taiga"}</button>
          <button onClick={() => {
            setFilters({
              sprintIds: [],
              statuses: [],
              assigneeIds: [],
              search: "",
              noSprintOnly: false,
              notAssignedQcOnly: false,
              assignedToMeOnly: false,
            });
            setItems([]);
            setEditingItemId(null);
            setEditDraft(null);
          }}>Clear Filters</button>
          <button onClick={async () => { await api.logout(); setLoggedIn(false); setMetadata(null); setItems([]); }}>Log out</button>
        </div>
      </header>

      {metadata ? (
        <>
          <section className="filters card">
            <MultiSelectDropdown
              label="Sprints"
              options={metadata.sprints.map((sprint) => ({ value: sprint.id, label: sprint.name }))}
              selectedValues={filters.sprintIds}
              onRemove={(value) =>
                setFilters((current) => ({
                  ...current,
                  sprintIds: current.sprintIds.filter((item) => item !== value),
                }))
              }
              onToggle={(value) =>
                setFilters((current) => ({
                  ...current,
                  sprintIds: current.sprintIds.includes(value)
                    ? current.sprintIds.filter((item) => item !== value)
                    : [...current.sprintIds, value],
                }))
              }
            />
            <MultiSelectDropdown
              label="Status"
              options={Array.from(new Set(Object.values(metadata.statuses).flat().map((status) => status.name))).map((status) => ({ value: status, label: status }))}
              selectedValues={filters.statuses}
              onRemove={(value) =>
                setFilters((current) => ({
                  ...current,
                  statuses: current.statuses.filter((item) => item !== value),
                }))
              }
              onToggle={(value) =>
                setFilters((current) => ({
                  ...current,
                  statuses: current.statuses.includes(value)
                    ? current.statuses.filter((item) => item !== value)
                    : [...current.statuses, value],
                }))
              }
            />
            <MultiSelectDropdown
              label="QC Assignees"
              options={metadata.users.map((user) => ({ value: user.id, label: user.full_name }))}
              selectedValues={filters.assigneeIds}
              onRemove={(value) =>
                setFilters((current) => ({
                  ...current,
                  assigneeIds: current.assigneeIds.filter((item) => item !== value),
                }))
              }
              onToggle={(value) =>
                setFilters((current) => ({
                  ...current,
                  assigneeIds: current.assigneeIds.includes(value)
                    ? current.assigneeIds.filter((item) => item !== value)
                    : [...current.assigneeIds, value],
                }))
              }
            />
            <div className="toggle-group">
              <label className="toggle-item"><input type="checkbox" checked={filters.noSprintOnly} onChange={() => setFilters((current) => ({ ...current, noSprintOnly: !current.noSprintOnly }))} /> No sprint</label>
              <label className="toggle-item"><input type="checkbox" checked={filters.notAssignedQcOnly} onChange={() => setFilters((current) => ({ ...current, notAssignedQcOnly: !current.notAssignedQcOnly }))} /> Not assigned QC</label>
              <label className="toggle-item"><input type="checkbox" checked={filters.assignedToMeOnly} onChange={() => setFilters((current) => ({ ...current, assignedToMeOnly: !current.assignedToMeOnly }))} /> Assign to me</label>
            </div>
          </section>
          <SelectedFilters
            metadata={metadata}
            filters={filters}
            onRemoveSprint={(id) => setFilters((current) => ({ ...current, sprintIds: current.sprintIds.filter((value) => value !== id) }))}
            onRemoveStatus={(value) => setFilters((current) => ({ ...current, statuses: current.statuses.filter((status) => status !== value) }))}
            onRemoveAssignee={(id) => setFilters((current) => ({ ...current, assigneeIds: current.assigneeIds.filter((value) => value !== id) }))}
            onClearSearch={() => setFilters((current) => ({ ...current, search: "" }))}
            onToggleNoSprint={() => setFilters((current) => ({ ...current, noSprintOnly: !current.noSprintOnly }))}
            onToggleNotAssignedQc={() => setFilters((current) => ({ ...current, notAssignedQcOnly: !current.notAssignedQcOnly }))}
            onToggleAssignedToMe={() => setFilters((current) => ({ ...current, assignedToMeOnly: !current.assignedToMeOnly }))}
          />
        </>
      ) : null}

      <nav className="tabs">
        {([
          ["userstory", "User Stories"],
          ["task", "Tasks"],
          ["issue", "Issues"],
        ] as [TabKey, string][]).map(([key, label]) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </nav>

      {metadata && hasActiveFilters ? (
        <>
          <SummaryBar
            items={items}
            onApplySummaryFilter={(kind) => {
              if (kind === "all") {
                return;
              }
              if (kind === "noSprint") {
                setFilters((current) => ({ ...current, noSprintOnly: true }));
                return;
              }
              if (kind === "missingQc") {
                setFilters((current) => ({ ...current, notAssignedQcOnly: true }));
                return;
              }
            }}
          />
          <ItemTable
            metadata={metadata}
            currentKind={tab}
            title={tab === "userstory" ? "User Stories" : tab === "task" ? "Tasks" : "Issues"}
            items={items}
            loading={itemsLoading}
            saving={savingItem !== null}
            editingItemId={editingItemId}
            draft={editDraft}
            onRefresh={() => void loadItems()}
            onExport={() => exportItems(items, `taiga-${tab}.xlsx`)}
            onStartEdit={handleStartEdit}
            onCancelEdit={() => { setEditingItemId(null); setEditDraft(null); }}
            onDraftChange={setEditDraft}
            onSaveEdit={(item) => void handleSaveEdit(item)}
          />
        </>
      ) : (
        <section className="card"><p>Select at least one filter to load items.</p></section>
      )}
      {error ? <pre className="error-box">{error}</pre> : null}
    </main>
  );
}
