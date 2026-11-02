import { useEffect, useState } from "react";
import type { ArtifactIdentity } from "../lib/artifactIdentity";
import { bookmarkRestoreStatus, INVESTIGATION_BOOKMARKS_KEY, investigationBookmarkKey, MAX_BOOKMARK_NOTE_LENGTH,
  portableBookmarkArtifact, readInvestigationBookmarks, saveInvestigationBookmark, validInvestigationTarget,
  type BookmarkReadResult, type InvestigationBookmark, type InvestigationPanel, type InvestigationTarget } from "../lib/investigationBookmarks";
import "./investigation-bookmarks.css";

export interface InvestigationBookmarksProps {
  artifactIdentity: ArtifactIdentity | null;
  currentTurn: number;
  target?: InvestigationTarget | null;
  panel?: InvestigationPanel;
  /** Root validates the saved index/name against the loaded bundle before seeking/selecting. */
  onRestore: (bookmark: InvestigationBookmark) => void;
}
function browserStorage(): Storage | null {
  try { return typeof window === "undefined" ? null : window.localStorage; } catch { return null; }
}
const load = () => readInvestigationBookmarks(browserStorage());

export function InvestigationBookmarks({ artifactIdentity, currentTurn, target = null, panel = "map", onRestore }: InvestigationBookmarksProps) {
  const [stored, setStored] = useState<BookmarkReadResult>(load);
  const artifact = portableBookmarkArtifact(artifactIdentity);
  const currentKey = artifact && target ? JSON.stringify([artifact.sha256, target.kind, target.index, currentTurn, panel]) : null;
  const [notes, setNotes] = useState(() => stored.ok ? stored.bookmarks.find((row) => investigationBookmarkKey(row) === currentKey)?.notes ?? "" : "");
  const [status, setStatus] = useState("");
  useEffect(() => {
    const refresh = (event: StorageEvent) => { if (event.key === INVESTIGATION_BOOKMARKS_KEY || event.key === null) setStored(load()); };
    window.addEventListener("storage", refresh);
    return () => window.removeEventListener("storage", refresh);
  }, []);
  const save = () => {
    const result = saveInvestigationBookmark(browserStorage(), artifactIdentity, target, currentTurn, panel, notes);
    if (!result.ok) { setStatus(result.error); return; }
    setStored({ ok: true, bookmarks: result.bookmarks });
    setStatus(result.updated ? "Existing bookmark updated. Your note remains in the draft." : "Bookmark saved locally. Your note remains in the draft.");
  };
  const restore = (bookmark: InvestigationBookmark) => {
    const checked = bookmarkRestoreStatus(bookmark, artifactIdentity);
    if (!checked.canRestore) { setStatus(checked.reason); return; }
    onRestore(bookmark);
    setStatus("Matching-file bookmark sent for entity, turn and panel restoration.");
  };
  const canSave = stored.ok && artifact !== null && validInvestigationTarget(target) && Number.isSafeInteger(currentTurn) && currentTurn >= 0;
  return <section className="investigation-bookmarks" aria-label="Investigation bookmarks">
    <h2>Investigation bookmarks</h2>
    <p>Save an entity, turn and panel against the original file's SHA-256. Bookmarks and optional notes stay in this browser.</p>
    {!artifact && <p>Saving and persisted restore require a verified raw-file SHA-256. Open a completed file first; live or in-memory worlds without a portable artifact identity are unsupported.</p>}
    {!target && <p>Select a region or civilization to save a bookmark.</p>}
    {artifact && target && <p>Current target: {target.name} ({target.kind}, index {target.index}), turn {currentTurn}, {panel}. File: {artifact.filename}.</p>}
    <label className="investigation-note">Private note (optional)<textarea aria-label="Private bookmark note" maxLength={MAX_BOOKMARK_NOTE_LENGTH} value={notes}
      onChange={(event) => setNotes(event.target.value)} rows={3} /></label>
    <p>{notes.length}/{MAX_BOOKMARK_NOTE_LENGTH} characters. Notes are private local input and are excluded from reference exports. Unsaved text is retained across target changes and errors; review it before saving.</p>
    <button type="button" onClick={save} disabled={!canSave}>Save current investigation</button>
    {!stored.ok && <div role="alert"><p>{stored.error}</p><button type="button" onClick={() => setStored(load())}>Retry reading bookmarks</button></div>}
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
