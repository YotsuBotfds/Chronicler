import { useEffect, useRef, useState } from "react";
import type { ArtifactIdentity } from "../lib/artifactIdentity";
import { bookmarkRestoreStatus, BOOKMARKS_CHANNEL, INVESTIGATION_BOOKMARKS_KEY, investigationBookmarkKey, MAX_BOOKMARK_NOTE_LENGTH,
  portableBookmarkArtifact, readStoredInvestigationBookmarks, saveInvestigationBookmark, validInvestigationTarget,
  type BookmarkReadResult, type InvestigationBookmark, type InvestigationPanel, type InvestigationTarget } from "../lib/investigationBookmarks";
import "./investigation-bookmarks.css";

export interface InvestigationBookmarksProps {
  artifactIdentity: ArtifactIdentity | null;
  currentTurn: number;
  target?: InvestigationTarget | null;
  panel?: InvestigationPanel;
  /** Root validates the saved index/name against the loaded bundle before seeking/selecting. */
  onRestore: (bookmark: InvestigationBookmark) => string | void;
}
function browserStorage(): Storage | null {
  try { return typeof window === "undefined" ? null : window.localStorage; } catch { return null; }
}
const load = () => readStoredInvestigationBookmarks(browserStorage());

export function InvestigationBookmarks({ artifactIdentity, currentTurn, target = null, panel = "map", onRestore }: InvestigationBookmarksProps) {
  const [stored, setStored] = useState<BookmarkReadResult>({ ok: false, bookmarks: [], error: "Loading local bookmarks…" });
  const artifact = portableBookmarkArtifact(artifactIdentity);
  const currentKey = artifact && target ? JSON.stringify([artifact.sha256, target.kind, target.index, currentTurn, panel]) : null;
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [readyKey, setReadyKey] = useState<string | null>(null);
  const baseline = useRef<InvestigationBookmark | null>(null);
  const firstLoad = useRef(true);
  const edited = useRef(false);
  const activeKey = useRef(currentKey);
  useEffect(() => {
    let active = true;
    activeKey.current = currentKey;
    void load().then((latest) => {
      if (!active) return;
      setStored(latest);
      baseline.current = latest.ok ? latest.bookmarks.find((row) => investigationBookmarkKey(row) === currentKey) ?? null : null;
      if (firstLoad.current && latest.ok) { if (!edited.current) setNotes(baseline.current?.notes ?? ""); firstLoad.current = false; }
      setReadyKey(currentKey);
    });
    return () => { active = false; };
  }, [currentKey]);
  useEffect(() => {
    const refresh = () => { void load().then(setStored); };
    const storage = (event: StorageEvent) => { if (event.key === INVESTIGATION_BOOKMARKS_KEY || event.key === null) refresh(); };
    window.addEventListener("storage", storage);
    let channel: BroadcastChannel | null = null;
    try { channel = new BroadcastChannel(BOOKMARKS_CHANNEL); channel.onmessage = refresh; } catch { /* reload remains available */ }
    return () => { window.removeEventListener("storage", storage); channel?.close(); };
  }, []);
  const save = async () => {
    setSaving(true);
    const result = await saveInvestigationBookmark(browserStorage(), artifactIdentity, target, currentTurn, panel, notes, baseline.current);
    setSaving(false);
    if (!result.ok) { setStatus(result.error); setConflict(result.error.startsWith("This bookmark changed")); setStored(await load()); return; }
    if (activeKey.current === currentKey) baseline.current = result.bookmark;
    setConflict(false);
    setStored(await load());
    setStatus(result.updated ? "Existing bookmark updated. Your note remains in the draft." : "Bookmark saved locally. Your note remains in the draft.");
  };
  const restore = (bookmark: InvestigationBookmark) => {
    const checked = bookmarkRestoreStatus(bookmark, artifactIdentity);
    if (!checked.canRestore) { setStatus(checked.reason); return; }
    const error = onRestore(bookmark);
    setStatus(error || "Matching-file bookmark restored to its entity, turn and panel.");
  };
  const canSave = stored.ok && readyKey === currentKey && artifact !== null && validInvestigationTarget(target) && Number.isSafeInteger(currentTurn) && currentTurn >= 0;
  return <section className="investigation-bookmarks" aria-label="Investigation bookmarks">
    <h2>Investigation bookmarks</h2>
    <p>Save an entity, turn and panel against the original file's SHA-256. Bookmarks and optional notes stay in this browser.</p>
    {!artifact && <p>Saving and persisted restore require a verified raw-file SHA-256. Open a completed file first; live or in-memory worlds without a portable artifact identity are unsupported.</p>}
    {!target && <p>Select a region or civilization to save a bookmark.</p>}
    {artifact && target && <p>Current target: {target.name} ({target.kind}, index {target.index}), turn {currentTurn}, {panel}. File: {artifact.filename}.</p>}
    <label className="investigation-note">Private note (optional)<textarea aria-label="Private bookmark note" maxLength={MAX_BOOKMARK_NOTE_LENGTH} value={notes} disabled={readyKey !== currentKey}
      onChange={(event) => { edited.current = true; setNotes(event.target.value); }} rows={3} /></label>
    <p>{notes.length}/{MAX_BOOKMARK_NOTE_LENGTH} characters. Notes are private local input and are excluded from reference exports. Unsaved text is retained across target changes and errors; review it before saving.</p>
    <button type="button" onClick={save} disabled={!canSave || saving}>Save current investigation</button>
    {conflict && <button type="button" onClick={async () => {
      const latest = await load(); setStored(latest);
      if (!latest.ok) { setStatus(latest.error); return; }
      baseline.current = latest.bookmarks.find((row) => investigationBookmarkKey(row) === currentKey) ?? null;
      setConflict(false); setStatus("Latest saved bookmark is shown below. Your draft is unchanged; save again to replace it.");
    }}>Review latest saved bookmark</button>}
    {!stored.ok && <div role="alert"><p>{stored.error}</p><button type="button" onClick={async () => { const latest = await load(); setStored(latest); if (latest.ok) setReadyKey(currentKey); }}>Retry reading bookmarks</button></div>}
    <p role="status">{status}</p>
    <h3>Saved locally ({stored.ok ? stored.bookmarks.length : "unavailable"}/50)</h3>
    {stored.ok && stored.bookmarks.length === 0 && <p>No saved investigations in this browser.</p>}
    {stored.ok && <ul className="investigation-bookmark-list">{stored.bookmarks.map((bookmark) => {
      const checked = bookmarkRestoreStatus(bookmark, artifactIdentity);
      const label = `${bookmark.target.name}, turn ${bookmark.turn}, ${bookmark.panel}`;
      return <li key={investigationBookmarkKey(bookmark)}>
        <h4>{bookmark.target.name} <small>({bookmark.target.kind}, index {bookmark.target.index})</small></h4>
        <p>Turn {bookmark.turn} · {bookmark.panel} · {bookmark.world.filename}</p>
        <details><summary>File SHA-256</summary><code>{bookmark.world.sha256}</code></details>
        {bookmark.notes !== undefined && <details><summary>Private note: {bookmark.target.name}, turn {bookmark.turn}</summary><p className="investigation-saved-note">{bookmark.notes}</p></details>}
        <p>{checked.reason}</p><button type="button" disabled={!checked.canRestore} onClick={() => restore(bookmark)} aria-label={`Restore bookmark: ${label}`}>Restore bookmark</button>
      </li>;
    })}</ul>}
  </section>;
}
