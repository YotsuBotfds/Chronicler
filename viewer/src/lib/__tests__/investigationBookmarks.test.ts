import { describe, expect, it } from "vitest";
import type { ArtifactIdentity } from "../artifactIdentity";
import { bookmarkRestoreStatus, INVESTIGATION_BOOKMARKS_KEY, investigationBookmarkReference, portableBookmarkArtifact,
  readInvestigationBookmarks, saveInvestigationBookmark, validInvestigationBookmark, type BookmarkStorage, type InvestigationBookmark } from "../investigationBookmarks";

const identity: ArtifactIdentity = { name: "world.json", byteLength: 123, sha256: "a".repeat(64) };
const target = { kind: "region" as const, index: 0, name: "Lowlands" };
const bookmark = (): InvestigationBookmark => ({ world: { sha256: "a".repeat(64), filename: "world.json" }, target, turn: 4, panel: "history", notes: "Private observation" });
function storage(initial: string | null = null) {
  let raw = initial, writes = 0;
  const api: BookmarkStorage = { getItem: () => raw, setItem: (_, value) => { raw = value; writes++; } };
  return { api, raw: () => raw, writes: () => writes };
}
const envelope = (bookmarks: InvestigationBookmark[]) => JSON.stringify({ version: 1, bookmarks });

describe("local investigation bookmark schema", () => {
  it("persists and reloads the exact artifact/target/turn/panel with optional private notes", () => {
    const saved = storage();
    expect(saveInvestigationBookmark(saved.api, identity, target, 4, "history", "Private observation")).toMatchObject({ ok: true, updated: false });
    expect(readInvestigationBookmarks(saved.api)).toEqual({ ok: true, bookmarks: [bookmark()] });
    expect(saved.raw()).not.toContain("byteLength");
    expect(saved.writes()).toBe(1);
  });
  it("requires the exact raw-file SHA rather than a seed, display name or matching array index", () => {
    const row = bookmark();
    expect(bookmarkRestoreStatus(row, identity).canRestore).toBe(true);
    expect(bookmarkRestoreStatus(row, { ...identity, name: "renamed-same-bytes.json" }).canRestore).toBe(true);
    expect(bookmarkRestoreStatus(row, { ...identity, sha256: "b".repeat(64) })).toMatchObject({ canRestore: false });
    expect(bookmarkRestoreStatus(row, null).reason).toContain(`Open matching file world.json with raw-file SHA-256 ${"a".repeat(64)}`);
    const local = storage();
    for (const artifact of [null, { ...identity, sha256: null }, { ...identity, sha256: "seed:42" }]) {
      expect(saveInvestigationBookmark(local.api, artifact, target, 4, "history").ok).toBe(false);
    }
    expect(local.writes()).toBe(0);
  });
  it("updates repeated saves without flooding and leaves notes out of share references", () => {
    const local = storage();
    saveInvestigationBookmark(local.api, identity, target, 4, "history", "First private note");
    const result = saveInvestigationBookmark(local.api, identity, { ...target, name: "Display label" }, 4, "history", "Revised private note");
    expect(result).toMatchObject({ ok: true, updated: true, bookmarks: [{ notes: "Revised private note" }] });
    const read = readInvestigationBookmarks(local.api);
    if (!read.ok) throw new Error(read.error);
    expect(read.bookmarks).toHaveLength(1);
    const reference = investigationBookmarkReference(read.bookmarks[0]);
    expect(reference).toEqual({ world: bookmark().world, target: { ...target, name: "Display label" }, turn: 4, panel: "history" });
    expect(JSON.stringify(reference)).not.toContain("private note");
    expect(read.bookmarks[0].notes).toBe("Revised private note");
  });
  it("stores only a bounded display filename rather than a supplied private path", () => {
    expect(portableBookmarkArtifact({ ...identity, name: "/private/session/output/world.json" })?.filename).toBe("world.json");
    expect(portableBookmarkArtifact({ ...identity, name: "C:\\private\\world.json" })?.filename).toBe("world.json");
    expect(portableBookmarkArtifact({ ...identity, name: "x".repeat(250) })?.filename).toHaveLength(200);
    const local = storage();
    saveInvestigationBookmark(local.api, { ...identity, name: "/private/world.json" }, target, 4, "history");
    expect(local.raw()).not.toContain("/private/");
    expect(Object.keys(JSON.parse(local.raw()!).bookmarks[0]).sort()).toEqual(["panel", "target", "turn", "world"]);
  });
  it.each(["not-json", JSON.stringify({ version: 2, bookmarks: [] }), JSON.stringify({ version: 1, bookmarks: [], rawBundle: {} }),
    envelope([{ ...bookmark(), notes: "x".repeat(1001) }]), envelope([{ ...bookmark(), turn: 1.5 }]),
    envelope([{ ...bookmark(), target: { ...target, index: -1 } }]), envelope([{ ...bookmark(), world: { ...bookmark().world, filename: "/private/world.json" } }]),
    envelope([{ ...bookmark(), world: { ...bookmark().world, filename: "x".repeat(201) } }]),
    envelope([bookmark(), bookmark()]), "x".repeat(120001)])("rejects corrupt/unsupported/bounds-invalid storage without overwriting: case %#", (raw) => {
    const local = storage(raw);
    expect(readInvestigationBookmarks(local.api).ok).toBe(false);
    expect(saveInvestigationBookmark(local.api, identity, target, 5, "map", "Unsaved note").ok).toBe(false);
    expect(local.raw()).toBe(raw);
    expect(local.writes()).toBe(0);
  });
  it("accepts the exact note/filename bounds and rejects extra payload fields", () => {
    const row = { ...bookmark(), notes: "x".repeat(1000), world: { ...bookmark().world, filename: "x".repeat(200) } };
    expect(readInvestigationBookmarks(storage(envelope([row])).api)).toEqual({ ok: true, bookmarks: [row] });
    expect(validInvestigationBookmark({ ...row, rawBundle: {} })).toBe(false);
    expect(validInvestigationBookmark({ ...row, world: { ...row.world, credential: "not accepted" } })).toBe(false);
  });
  it("enforces fifty records while allowing updates and preserving old storage on the cap", () => {
    const records = Array.from({ length: 50 }, (_, turn) => ({ ...bookmark(), turn }));
    const local = storage(envelope(records));
    const before = local.raw();
    expect(saveInvestigationBookmark(local.api, identity, target, 50, "history", "New note")).toMatchObject({ ok: false });
    expect(local.raw()).toBe(before);
    expect(saveInvestigationBookmark(local.api, identity, target, 1, "history", "Updated note")).toMatchObject({ ok: true, updated: true });
    const oversized = storage(envelope([...records, { ...bookmark(), turn: 50 }]));
    expect(readInvestigationBookmarks(oversized.api).ok).toBe(false);
  });
  it("reports quota/read errors and never performs cleanup or exposes exception text", () => {
    const throwing: BookmarkStorage = { getItem: () => envelope([bookmark()]), setItem: () => { throw new Error("/private/secret/path"); } };
    const result = saveInvestigationBookmark(throwing, identity, target, 5, "history", "Keep my note");
    expect(result).toMatchObject({ ok: false });
    expect(JSON.stringify(result)).toContain("storage may be blocked or full");
    expect(JSON.stringify(result)).not.toContain("/private/");
    expect(readInvestigationBookmarks({ ...throwing, getItem: () => { throw new Error("denied"); } }).ok).toBe(false);
    expect(readInvestigationBookmarks(null).ok).toBe(false);
  });
  it("re-reads current storage before saving and strictly validates restore targets", () => {
    const local = storage(envelope([bookmark()]));
    const current = { ...bookmark(), turn: 8 };
    local.api.setItem(INVESTIGATION_BOOKMARKS_KEY, envelope([bookmark(), current]));
    expect(saveInvestigationBookmark(local.api, identity, target, 9, "map")).toMatchObject({ ok: true, bookmarks: [{ turn: 9 }, { turn: 4 }, { turn: 8 }] });
    const malformed = { ...bookmark(), target: { ...target, kind: "unknown" } };
    expect(validInvestigationBookmark(malformed)).toBe(false);
    expect(bookmarkRestoreStatus(malformed as InvestigationBookmark, identity).canRestore).toBe(false);
    expect(investigationBookmarkReference(malformed as InvestigationBookmark)).toBeNull();
  });
});
