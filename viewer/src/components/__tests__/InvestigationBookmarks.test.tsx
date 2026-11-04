import { bookmarkIdbStub } from "../../lib/__tests__/bookmarkIdbStub";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactIdentity } from "../../lib/artifactIdentity";
import { INVESTIGATION_BOOKMARKS_KEY, saveInvestigationBookmark, type InvestigationBookmark } from "../../lib/investigationBookmarks";
import { InvestigationBookmarks } from "../InvestigationBookmarks";

const identity: ArtifactIdentity = { name: "world.json", byteLength: 123, sha256: "a".repeat(64) };
const target = { kind: "civilization" as const, index: 1, name: "Marsh Realm" };
const saved: InvestigationBookmark = { world: { sha256: "a".repeat(64), filename: "world.json" }, target, turn: 4, panel: "history", notes: "Keep this private note" };
const seed = () => localStorage.setItem(INVESTIGATION_BOOKMARKS_KEY, JSON.stringify({ version: 1, bookmarks: [saved] }));
let db: ReturnType<typeof bookmarkIdbStub>;
beforeEach(() => { localStorage.clear(); db = bookmarkIdbStub(); vi.stubGlobal("indexedDB", db.factory); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); });

describe("Investigation bookmarks", () => {
  it("keeps the observed baseline and draft after a storage notification until explicit conflict review", async () => {
    seed();
    render(<InvestigationBookmarks artifactIdentity={identity} currentTurn={4} target={target} panel="history" onRestore={vi.fn()} />);
    await screen.findByRole("heading", { name: "Saved locally (1/50)" });
    fireEvent.change(screen.getByRole("textbox", { name: "Private bookmark note" }), { target: { value: "My draft" } });
    await act(async () => {
      expect((await saveInvestigationBookmark(localStorage, identity, target, 4, "history", "Other tab", saved)).ok).toBe(true);
      window.dispatchEvent(new StorageEvent("storage", { key: INVESTIGATION_BOOKMARKS_KEY }));
    });
    await screen.findByText("Other tab");
    fireEvent.click(screen.getByRole("button", { name: "Save current investigation" }));
    await screen.findByRole("button", { name: "Review latest saved bookmark" });
    expect(screen.getByRole("textbox", { name: "Private bookmark note" })).toHaveValue("My draft");
    fireEvent.click(screen.getByRole("button", { name: "Review latest saved bookmark" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Latest saved bookmark"));
    fireEvent.click(screen.getByRole("button", { name: "Save current investigation" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Existing bookmark updated"));
    expect(JSON.parse(db.raw()!).bookmarks[0].notes).toBe("My draft");
  });
  it("saves notes locally, makes duplicate clicks idempotent and restores through a deliberate callback", async () => {
    const restore = vi.fn();
    render(<InvestigationBookmarks artifactIdentity={identity} currentTurn={4} target={target} panel="history" onRestore={restore} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Save current investigation" })).toBeEnabled());
    fireEvent.change(screen.getByRole("textbox", { name: "Private bookmark note" }), { target: { value: "Keep this private note" } });
    const save = screen.getByRole("button", { name: "Save current investigation" });
    fireEvent.click(save);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Bookmark saved locally"));
    fireEvent.click(save);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Existing bookmark updated"));
    expect(JSON.parse(db.raw()!).bookmarks).toEqual([saved]);
    expect(screen.getByRole("status")).toHaveTextContent("Existing bookmark updated");
    expect(restore).not.toHaveBeenCalled();
    const button = screen.getByRole("button", { name: "Restore bookmark: Marsh Realm, turn 4, history" });
    button.focus(); expect(button).toHaveFocus();
    fireEvent.click(button);
    expect(restore).toHaveBeenCalledExactlyOnceWith(saved);
  });
  it("shows saved bookmarks/notes after reload without loading a world and prevents restore", async () => {
    seed();
    const restore = vi.fn();
    render(<InvestigationBookmarks artifactIdentity={null} currentTurn={0} onRestore={restore} />);
    await screen.findByRole("heading", { name: "Saved locally (1/50)" });
    fireEvent.click(screen.getByText("Private note: Marsh Realm, turn 4"));
    expect(screen.getByText("Keep this private note")).toBeVisible();
    expect(screen.getByText(/Open matching file world.json with raw-file SHA-256/)).toHaveTextContent("a".repeat(64));
    const button = screen.getByRole("button", { name: /Restore bookmark:/ });
    expect(button).toBeDisabled(); fireEvent.click(button);
    expect(restore).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save current investigation" })).toBeDisabled();
  });
  it("keeps the wrong loaded world and unsaved note until the exact matching artifact is opened", async () => {
    seed();
    const restore = vi.fn();
    const props = { currentTurn: 8, target, onRestore: restore };
    const view = render(<InvestigationBookmarks {...props} artifactIdentity={{ ...identity, sha256: "b".repeat(64) }} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Private bookmark note" }), { target: { value: "Unsaved draft" } });
    await screen.findByRole("button", { name: /Restore bookmark:/ });
    expect(screen.getByRole("button", { name: /Restore bookmark:/ })).toBeDisabled();
    expect(screen.getByText(/The loaded file differs; your current world is kept/)).toBeInTheDocument();
    expect(restore).not.toHaveBeenCalled();
    view.rerender(<InvestigationBookmarks {...props} artifactIdentity={identity} />);
    expect(screen.getByRole("textbox", { name: "Private bookmark note" })).toHaveValue("Unsaved draft");
    expect(screen.getByRole("button", { name: /Restore bookmark:/ })).toBeEnabled();
  });
  it("preserves corrupt/unknown-version storage and draft text on retry without cleanup", async () => {
    const raw = JSON.stringify({ version: 2, bookmarks: [] });
    localStorage.setItem(INVESTIGATION_BOOKMARKS_KEY, raw);
    render(<InvestigationBookmarks artifactIdentity={identity} currentTurn={4} target={target} onRestore={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("version is unsupported"));
    expect(screen.getByRole("button", { name: "Save current investigation" })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Private bookmark note" }), { target: { value: "Retain this draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Retry reading bookmarks" }));
    expect(localStorage.getItem(INVESTIGATION_BOOKMARKS_KEY)).toBe(raw);
    expect(screen.getByRole("textbox", { name: "Private bookmark note" })).toHaveValue("Retain this draft");
  });
  it("keeps the saved list and unsaved text when storage quota rejects the explicit save", async () => {
    seed();
    const before = localStorage.getItem(INVESTIGATION_BOOKMARKS_KEY);
    render(<InvestigationBookmarks artifactIdentity={identity} currentTurn={8} target={target} onRestore={vi.fn()} />);
    await screen.findByRole("heading", { name: "Saved locally (1/50)" });
    fireEvent.change(screen.getByRole("textbox", { name: "Private bookmark note" }), { target: { value: "Do not lose this" } });
    db.failWrites(true);
    fireEvent.click(screen.getByRole("button", { name: "Save current investigation" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("storage failed"));
    expect(screen.getByRole("textbox", { name: "Private bookmark note" })).toHaveValue("Do not lose this");
    expect(screen.getByRole("heading", { name: "Saved locally (1/50)" })).toBeInTheDocument();
    expect(localStorage.getItem(INVESTIGATION_BOOKMARKS_KEY)).toBe(before);
  });
  it("does not invent persisted identity for live/in-memory worlds or store raw bundle state", () => {
    render(<InvestigationBookmarks artifactIdentity={{ ...identity, sha256: null }} currentTurn={4} target={target} onRestore={vi.fn()} />);
    expect(screen.getByText(/live or in-memory worlds without a portable artifact identity are unsupported/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Private bookmark note" })).toHaveAttribute("maxlength", "1000");
    expect(screen.getByRole("button", { name: "Save current investigation" })).toBeDisabled();
    expect(localStorage.length).toBe(0);
  });
});
