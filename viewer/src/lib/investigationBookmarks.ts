/** Local, artifact-bound investigation bookmarks. Notes never enter reference exports. */
import type { ArtifactIdentity } from "./artifactIdentity";

export const INVESTIGATION_BOOKMARKS_KEY = "chronicler.investigation-bookmarks.v1";
export const MAX_INVESTIGATION_BOOKMARKS = 50;
export const MAX_BOOKMARK_NOTE_LENGTH = 1000;
export type InvestigationPanel = "map" | "history" | "conditions";
export interface InvestigationTarget { kind: "region" | "civilization"; index: number; name: string }
export interface InvestigationBookmark {
  world: { sha256: string; filename: string };
  target: InvestigationTarget;
  turn: number;
  panel: InvestigationPanel;
  notes?: string;
}
export interface BookmarkStorage { getItem: (key: string) => string | null; setItem: (key: string, value: string) => void }
export type BookmarkReadResult = { ok: true; bookmarks: InvestigationBookmark[] } | { ok: false; bookmarks: []; error: string };
export type BookmarkSaveResult = { ok: true; bookmarks: InvestigationBookmark[]; bookmark: InvestigationBookmark; updated: boolean }
  | { ok: false; error: string };
const object = (value: unknown): Record<string, unknown> | null => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
const keysAre = (row: Record<string, unknown>, required: string[], optional: string[] = []) => required.every((key) => Object.hasOwn(row, key))
  && Object.keys(row).every((key) => required.includes(key) || optional.includes(key));
const hash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const safeInteger = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const label = (value: unknown, max: number): value is string => typeof value === "string" && value.trim().length > 0 && value.length <= max && !/\p{Cc}/u.test(value);
export function validInvestigationTarget(value: unknown): value is InvestigationTarget {
  const row = object(value);
  return !!row && keysAre(row, ["kind", "index", "name"]) && (row.kind === "region" || row.kind === "civilization")
    && safeInteger(row.index) && label(row.name, 200);
}
export function validInvestigationPanel(value: unknown): value is InvestigationPanel { return value === "map" || value === "history" || value === "conditions"; }
export function validInvestigationBookmark(value: unknown): value is InvestigationBookmark {
  const row = object(value), world = object(row?.world);
  return !!row && !!world && keysAre(row, ["world", "target", "turn", "panel"], ["notes"])
    && keysAre(world, ["sha256", "filename"]) && hash(world.sha256) && label(world.filename, 200) && !/[/\\]/.test(world.filename)
    && validInvestigationTarget(row.target) && safeInteger(row.turn) && validInvestigationPanel(row.panel)
    && (!Object.hasOwn(row, "notes") || typeof row.notes === "string" && row.notes.length <= MAX_BOOKMARK_NOTE_LENGTH);
}
/** Stable key excludes the editable label/note and never uses a seed or world name. */
export function investigationBookmarkKey(bookmark: InvestigationBookmark): string {
  return JSON.stringify([bookmark.world.sha256, bookmark.target.kind, bookmark.target.index, bookmark.turn, bookmark.panel]);
}
export function readInvestigationBookmarks(storage: BookmarkStorage | null): BookmarkReadResult {
  if (!storage) return { ok: false, bookmarks: [], error: "Local bookmark storage is unavailable. Existing data and unsaved notes are kept." };
  let raw: string | null;
  try { raw = storage.getItem(INVESTIGATION_BOOKMARKS_KEY); }
  catch { return { ok: false, bookmarks: [], error: "Local bookmarks could not be read. Existing data and unsaved notes are kept." }; }
  if (raw === null) return { ok: true, bookmarks: [] };
  if (raw.length > 120000) return { ok: false, bookmarks: [], error: "Stored bookmarks exceed the supported size. Existing data was kept; no cleanup was performed." };
  let parsed: unknown;
  try { parsed = JSON.parse(raw); }
  catch { return { ok: false, bookmarks: [], error: "Stored bookmarks are corrupt JSON. Existing data was kept; no cleanup was performed." }; }
  const row = object(parsed);
  if (row && row.version !== 1) return { ok: false, bookmarks: [], error: "Stored bookmark version is unsupported. Existing data was kept; no cleanup was performed." };
  if (!row || !keysAre(row, ["version", "bookmarks"]) || row.version !== 1 || !Array.isArray(row.bookmarks)
    || row.bookmarks.length > MAX_INVESTIGATION_BOOKMARKS || !row.bookmarks.every(validInvestigationBookmark)) {
    return { ok: false, bookmarks: [], error: "Stored bookmark schema or bounds are invalid. Existing data was kept; no cleanup was performed." };
  }
  const bookmarks = row.bookmarks as InvestigationBookmark[];
  if (new Set(bookmarks.map(investigationBookmarkKey)).size !== bookmarks.length)
    return { ok: false, bookmarks: [], error: "Stored bookmark keys are duplicated. Existing data was kept; no cleanup was performed." };
  return { ok: true, bookmarks };
}

/** ArtifactIdentity's SHA is over original file bytes. A display label alone never binds a world. */
export function portableBookmarkArtifact(identity: ArtifactIdentity | null): InvestigationBookmark["world"] | null {
  if (!identity || !hash(identity.sha256) || typeof identity.name !== "string") return null;
  const basename = identity.name.split(/[/\\]/).at(-1)?.replace(/\p{Cc}/gu, "").trim().slice(0, 200) || "Unnamed artifact";
  return { sha256: identity.sha256, filename: basename };
}
export function bookmarkRestoreStatus(bookmark: InvestigationBookmark, identity: ArtifactIdentity | null): { canRestore: boolean; reason: string } {
  if (!validInvestigationBookmark(bookmark)) return { canRestore: false, reason: "Bookmark target or schema is invalid; restore was refused." };
  const artifact = portableBookmarkArtifact(identity);
  if (!artifact) return { canRestore: false, reason: `Open matching file ${bookmark.world.filename} with raw-file SHA-256 ${bookmark.world.sha256}. Live or in-memory worlds without a verified artifact hash cannot restore persisted bookmarks.` };
  if (artifact.sha256 !== bookmark.world.sha256) return { canRestore: false, reason: `Open matching file ${bookmark.world.filename} with raw-file SHA-256 ${bookmark.world.sha256}. The loaded file differs; your current world is kept.` };
  return { canRestore: true, reason: "Loaded file SHA-256 matches. Restore will select the saved entity, turn and panel." };
}

export function saveInvestigationBookmark(storage: BookmarkStorage | null, identity: ArtifactIdentity | null, target: InvestigationTarget | null,
  turn: number, panel: InvestigationPanel, notes = ""): BookmarkSaveResult {
  const world = portableBookmarkArtifact(identity);
  if (!world) return { ok: false, error: "Save requires a verified raw-file SHA-256. Live or in-memory worlds without that artifact identity cannot persist a portable bookmark." };
  const bookmark = { world, target, turn, panel, ...(notes.length ? { notes } : {}) };
  if (!validInvestigationBookmark(bookmark)) return { ok: false, error: "Bookmark target, turn, panel or note is invalid. Notes may contain at most 1000 characters; names at most 200." };
  // Re-read immediately before writing so a stale mounted list cannot silently
  // discard another tab's saved records. Invalid data is never overwritten.
  const previous = readInvestigationBookmarks(storage);
  if (!previous.ok) return { ok: false, error: previous.error };
  const key = investigationBookmarkKey(bookmark), existing = previous.bookmarks.findIndex((row) => investigationBookmarkKey(row) === key);
  if (existing < 0 && previous.bookmarks.length >= MAX_INVESTIGATION_BOOKMARKS)
    return { ok: false, error: "The local limit is 50 bookmarks. Existing bookmarks and your unsaved note are kept; a new bookmark was not saved." };
  const bookmarks = [...previous.bookmarks];
  if (existing >= 0) bookmarks[existing] = bookmark; else bookmarks.unshift(bookmark);
  try { storage!.setItem(INVESTIGATION_BOOKMARKS_KEY, JSON.stringify({ version: 1, bookmarks })); }
  catch { return { ok: false, error: "Bookmark save failed (storage may be blocked or full). Existing bookmarks and your unsaved note are kept. You can retry." }; }
  return { ok: true, bookmarks, bookmark, updated: existing >= 0 };
}

/** Safe reference for optional future sharing. Private notes are excluded by construction. */
export function investigationBookmarkReference(bookmark: InvestigationBookmark): Omit<InvestigationBookmark, "notes"> | null {
  return validInvestigationBookmark(bookmark) ? { world: { sha256: bookmark.world.sha256, filename: bookmark.world.filename },
    target: { kind: bookmark.target.kind, index: bookmark.target.index, name: bookmark.target.name }, turn: bookmark.turn, panel: bookmark.panel } : null;
}
