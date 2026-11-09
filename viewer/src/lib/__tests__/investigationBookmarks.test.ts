import { bookmarkIdbStub } from "./bookmarkIdbStub";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactIdentity } from "../artifactIdentity";
import { bookmarkRestoreStatus, INVESTIGATION_BOOKMARKS_KEY, investigationBookmarkKey, portableBookmarkArtifact,
  readInvestigationBookmarks, readStoredInvestigationBookmarks, saveInvestigationBookmark as saveWithLock, validInvestigationBookmark, type BookmarkStorage, type InvestigationBookmark } from "../investigationBookmarks";

const identity: ArtifactIdentity = { name: "world.json", byteLength: 123, sha256: "a".repeat(64) };
const target = { kind: "region" as const, index: 0, name: "Lowlands" };
const bookmark = (): InvestigationBookmark => ({ world: { sha256: "a".repeat(64), filename: "world.json" }, target, turn: 4, panel: "history", notes: "Private observation" });
function storage(initial: string | null = null) {
  let raw = initial, writes = 0;
  const api: BookmarkStorage = { getItem: () => raw, setItem: (_, value) => { raw = value; writes++; } };
  return { api, raw: () => raw, writes: () => writes };
}
let db: ReturnType<typeof bookmarkIdbStub>;
beforeEach(() => { db = bookmarkIdbStub(); vi.stubGlobal("indexedDB", db.factory); });
async function saveInvestigationBookmark(storage: BookmarkStorage | null, identity: ArtifactIdentity | null, target: { kind: "region" | "civilization"; index: number; name: string } | null, turn: number, panel: "map" | "history" | "conditions", notes = "") {
  const current = await readStoredInvestigationBookmarks(storage);
  const world = portableBookmarkArtifact(identity);
  const key = world && target ? investigationBookmarkKey({ world, target, turn, panel }) : null;
  const expected = current.ok ? current.bookmarks.find((row) => investigationBookmarkKey(row) === key) ?? null : null;
  return saveWithLock(storage, identity, target, turn, panel, notes, expected);
}
const envelope = (bookmarks: InvestigationBookmark[]) => JSON.stringify({ version: 1, bookmarks });

describe("local investigation bookmark schema", () => {
  it("fails closed when IndexedDB is unavailable or its upgrade is blocked", async () => {
    const local = storage(envelope([bookmark()]));
    vi.stubGlobal("indexedDB", undefined);
    expect(await readStoredInvestigationBookmarks(local.api)).toMatchObject({ ok: false });
    const blocked = { open: () => {
      const request: { onblocked?: () => void } = {};
      setTimeout(() => request.onblocked?.(), 0);
      return request;
    } };
    vi.stubGlobal("indexedDB", blocked);
    expect(await readStoredInvestigationBookmarks(local.api)).toMatchObject({ ok: false });
    expect(local.raw()).toBe(envelope([bookmark()]));
  });
  it("persists and reloads the exact artifact/target/turn/panel with optional private notes", async () => {
    const saved = storage();
    expect(await saveInvestigationBookmark(saved.api, identity, target, 4, "history", "Private observation")).toMatchObject({ ok: true, updated: false });
    expect(await readStoredInvestigationBookmarks(saved.api)).toEqual({ ok: true, bookmarks: [bookmark()] });
    expect(db.raw()).not.toContain("byteLength");
    expect(saved.writes()).toBe(0);
  });
  it("requires the exact raw-file SHA rather than a seed, display name or matching array index", async () => {
    const row = bookmark();
    expect(bookmarkRestoreStatus(row, identity).canRestore).toBe(true);
    expect(bookmarkRestoreStatus(row, { ...identity, name: "renamed-same-bytes.json" }).canRestore).toBe(true);
    expect(bookmarkRestoreStatus(row, { ...identity, sha256: "b".repeat(64) })).toMatchObject({ canRestore: false });
    expect(bookmarkRestoreStatus(row, null).reason).toContain(`Open matching file world.json with raw-file SHA-256 ${"a".repeat(64)}`);
    const local = storage();
    for (const artifact of [null, { ...identity, sha256: null }, { ...identity, sha256: "seed:42" }]) {
      expect((await saveInvestigationBookmark(local.api, artifact, target, 4, "history")).ok).toBe(false);
    }
    expect(local.writes()).toBe(0);
  });
  it("updates repeated saves without flooding and leaves notes out of share references", async () => {
    const local = storage();
    await saveInvestigationBookmark(local.api, identity, target, 4, "history", "First private note");
    const result = await saveInvestigationBookmark(local.api, identity, { ...target, name: "Display label" }, 4, "history", "Revised private note");
    expect(result).toMatchObject({ ok: true, updated: true, bookmarks: [{ notes: "Revised private note" }] });
    const read = await readStoredInvestigationBookmarks(local.api);
    if (!read.ok) throw new Error(read.error);
    expect(read.bookmarks).toHaveLength(1);
    expect(read.bookmarks[0]).toMatchObject({ world: bookmark().world, target: { ...target, name: "Display label" }, turn: 4, panel: "history" });
    expect(read.bookmarks[0].notes).toBe("Revised private note");
  });
  it("stores only a bounded display filename rather than a supplied private path", async () => {
    expect(portableBookmarkArtifact({ ...identity, name: "/private/session/output/world.json" })?.filename).toBe("world.json");
    expect(portableBookmarkArtifact({ ...identity, name: "C:\\private\\world.json" })?.filename).toBe("world.json");
    expect(portableBookmarkArtifact({ ...identity, name: "x".repeat(250) })?.filename).toHaveLength(200);
    const local = storage();
    await saveInvestigationBookmark(local.api, { ...identity, name: "/private/world.json" }, target, 4, "history");
    expect(db.raw()).not.toContain("/private/");
    expect(Object.keys(JSON.parse(db.raw()!).bookmarks[0]).sort()).toEqual(["panel", "target", "turn", "world"]);
  });
  it.each(["not-json", JSON.stringify({ version: 2, bookmarks: [] }), JSON.stringify({ version: 1, bookmarks: [], rawBundle: {} }),
    envelope([{ ...bookmark(), notes: "x".repeat(1001) }]), envelope([{ ...bookmark(), turn: 1.5 }]),
    envelope([{ ...bookmark(), target: { ...target, index: -1 } }]), envelope([{ ...bookmark(), world: { ...bookmark().world, filename: "/private/world.json" } }]),
    envelope([{ ...bookmark(), world: { ...bookmark().world, filename: "x".repeat(201) } }]),
    envelope([bookmark(), bookmark()]), "x".repeat(120001)])("rejects corrupt/unsupported/bounds-invalid storage without overwriting: case %#", async (raw) => {
    const local = storage(raw);
    expect(readInvestigationBookmarks(local.api).ok).toBe(false);
    expect((await saveInvestigationBookmark(local.api, identity, target, 5, "map", "Unsaved note")).ok).toBe(false);
    expect(local.raw()).toBe(raw);
    expect(local.writes()).toBe(0);
  });
  it("accepts the exact note/filename bounds and rejects extra payload fields", async () => {
    const row = { ...bookmark(), notes: "x".repeat(1000), world: { ...bookmark().world, filename: "x".repeat(200) } };
    expect(readInvestigationBookmarks(storage(envelope([row])).api)).toEqual({ ok: true, bookmarks: [row] });
    expect(validInvestigationBookmark({ ...row, rawBundle: {} })).toBe(false);
    expect(validInvestigationBookmark({ ...row, world: { ...row.world, credential: "not accepted" } })).toBe(false);
  });
  it("enforces fifty records while allowing updates and preserving old storage on the cap", async () => {
    const records = Array.from({ length: 50 }, (_, turn) => ({ ...bookmark(), turn }));
    const local = storage(envelope(records));
    const before = local.raw();
    expect(await saveInvestigationBookmark(local.api, identity, target, 50, "history", "New note")).toMatchObject({ ok: false });
    expect(local.raw()).toBe(before);
    expect(await saveInvestigationBookmark(local.api, identity, target, 1, "history", "Updated note")).toMatchObject({ ok: true, updated: true });
    const oversized = storage(envelope([...records, { ...bookmark(), turn: 50 }]));
    expect(readInvestigationBookmarks(oversized.api).ok).toBe(false);
  });
  it("reports quota/read errors and never performs cleanup or exposes exception text", async () => {
    const throwing: BookmarkStorage = { getItem: () => envelope([bookmark()]), setItem: () => { throw new Error("/private/secret/path"); } };
    db.failWrites(true);
    const result = await saveInvestigationBookmark(throwing, identity, target, 5, "history", "Keep my note");
    expect(result).toMatchObject({ ok: false });
    expect(JSON.stringify(result)).toContain("storage may be blocked or full");
    expect(JSON.stringify(result)).not.toContain("/private/");
    expect(readInvestigationBookmarks({ ...throwing, getItem: () => { throw new Error("denied"); } }).ok).toBe(false);
    expect(readInvestigationBookmarks(null).ok).toBe(false);
  });
  it("re-reads current storage before saving and strictly validates restore targets", async () => {
    const local = storage(envelope([bookmark()]));
    const current = { ...bookmark(), turn: 8 };
    local.api.setItem(INVESTIGATION_BOOKMARKS_KEY, envelope([bookmark(), current]));
    expect(await saveInvestigationBookmark(local.api, identity, target, 9, "map")).toMatchObject({ ok: true, bookmarks: [{ turn: 9 }, { turn: 4 }, { turn: 8 }] });
    const malformed = { ...bookmark(), target: { ...target, kind: "unknown" } };
    expect(validInvestigationBookmark(malformed)).toBe(false);
    expect(bookmarkRestoreStatus(malformed as InvestigationBookmark, identity).canRestore).toBe(false);
  });
});
