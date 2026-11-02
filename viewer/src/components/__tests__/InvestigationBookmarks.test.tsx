import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactIdentity } from "../../lib/artifactIdentity";
import { INVESTIGATION_BOOKMARKS_KEY, type InvestigationBookmark } from "../../lib/investigationBookmarks";
import { InvestigationBookmarks } from "../InvestigationBookmarks";

const identity: ArtifactIdentity = { name: "world.json", byteLength: 123, sha256: "a".repeat(64) };
const target = { kind: "civilization" as const, index: 1, name: "Marsh Realm" };
const saved: InvestigationBookmark = { world: { sha256: "a".repeat(64), filename: "world.json" }, target, turn: 4, panel: "history", notes: "Keep this private note" };
const seed = () => localStorage.setItem(INVESTIGATION_BOOKMARKS_KEY, JSON.stringify({ version: 1, bookmarks: [saved] }));
beforeEach(() => localStorage.clear());
afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); });

describe("Investigation bookmarks", () => {
  it("saves notes locally, makes duplicate clicks idempotent and restores through a deliberate callback", () => {
    const restore = vi.fn();
    render(<InvestigationBookmarks artifactIdentity={identity} currentTurn={4} target={target} panel="history" onRestore={restore} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Private bookmark note" }), { target: { value: "Keep this private note" } });
    const save = screen.getByRole("button", { name: "Save current investigation" });
    fireEvent.click(save); fireEvent.click(save);
    expect(JSON.parse(localStorage.getItem(INVESTIGATION_BOOKMARKS_KEY)!).bookmarks).toEqual([saved]);
    expect(screen.getByRole("status")).toHaveTextContent("Existing bookmark updated");
    expect(restore).not.toHaveBeenCalled();
    const button = screen.getByRole("button", { name: "Restore bookmark: Marsh Realm, turn 4, history" });
    button.focus(); expect(button).toHaveFocus();
    fireEvent.click(button);
    expect(restore).toHaveBeenCalledExactlyOnceWith(saved);
  });
  it("shows saved bookmarks/notes after reload without loading a world and prevents restore", () => {
    seed();
    const restore = vi.fn();
    render(<InvestigationBookmarks artifactIdentity={null} currentTurn={0} onRestore={restore} />);
    expect(screen.getByRole("heading", { name: "Saved locally (1/50)" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Private note: Marsh Realm, turn 4"));
    expect(screen.getByText("Keep this private note")).toBeVisible();
    expect(screen.getByText(/Open matching file world.json with raw-file SHA-256/)).toHaveTextContent("a".repeat(64));
    const button = screen.getByRole("button", { name: /Restore bookmark:/ });
    expect(button).toBeDisabled(); fireEvent.click(button);
    expect(restore).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save current investigation" })).toBeDisabled();
  });
  it("keeps the wrong loaded world and unsaved note until the exact matching artifact is opened", () => {
    seed();
    const restore = vi.fn();
    const props = { currentTurn: 8, target, onRestore: restore };
    const view = render(<InvestigationBookmarks {...props} artifactIdentity={{ ...identity, sha256: "b".repeat(64) }} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Private bookmark note" }), { target: { value: "Unsaved draft" } });
    expect(screen.getByRole("button", { name: /Restore bookmark:/ })).toBeDisabled();
    expect(screen.getByText(/The loaded file differs; your current world is kept/)).toBeInTheDocument();
    expect(restore).not.toHaveBeenCalled();
    view.rerender(<InvestigationBookmarks {...props} artifactIdentity={identity} />);
    expect(screen.getByRole("textbox", { name: "Private bookmark note" })).toHaveValue("Unsaved draft");
    expect(screen.getByRole("button", { name: /Restore bookmark:/ })).toBeEnabled();
  });
  it("preserves corrupt/unknown-version storage and draft text on retry without cleanup", () => {
    const raw = JSON.stringify({ version: 2, bookmarks: [] });
    localStorage.setItem(INVESTIGATION_BOOKMARKS_KEY, raw);
    render(<InvestigationBookmarks artifactIdentity={identity} currentTurn={4} target={target} onRestore={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("version is unsupported");
    expect(screen.getByRole("button", { name: "Save current investigation" })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Private bookmark note" }), { target: { value: "Retain this draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Retry reading bookmarks" }));
    expect(localStorage.getItem(INVESTIGATION_BOOKMARKS_KEY)).toBe(raw);
    expect(screen.getByRole("textbox", { name: "Private bookmark note" })).toHaveValue("Retain this draft");
  });
  it("keeps the saved list and unsaved text when storage quota rejects the explicit save", () => {
    seed();
    const before = localStorage.getItem(INVESTIGATION_BOOKMARKS_KEY);
    render(<InvestigationBookmarks artifactIdentity={identity} currentTurn={8} target={target} onRestore={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Private bookmark note" }), { target: { value: "Do not lose this" } });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
    fireEvent.click(screen.getByRole("button", { name: "Save current investigation" }));
    expect(screen.getByRole("status")).toHaveTextContent("save failed");
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
