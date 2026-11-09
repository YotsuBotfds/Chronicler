import { afterEach, describe, expect, it, vi } from "vitest";
import { downloadText } from "../download";

const original = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };

describe("downloadText", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    Object.assign(URL, { createObjectURL: original.create, revokeObjectURL: original.revoke });
  });

  it("clicks a link to an object URL of the text and revokes it a second later", async () => {
    vi.useFakeTimers();
    const blobs: Blob[] = [];
    const create = vi.fn((blob: Blob) => { blobs.push(blob); return "blob:packet"; });
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { clicked.push(this); });

    downloadText("packet.md", "# Packet", "text/markdown");

    expect(create).toHaveBeenCalledTimes(1);
    expect(blobs[0].type).toBe("text/markdown");
    expect(await blobs[0].text()).toBe("# Packet");
    expect(clicked).toHaveLength(1);
    expect(clicked[0].href).toBe("blob:packet");
    expect(clicked[0].download).toBe("packet.md");
    vi.advanceTimersByTime(999);
    expect(revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(revoke).toHaveBeenCalledWith("blob:packet");
  });

  it("revokes after the delay a caller passes", () => {
    vi.useFakeTimers();
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: () => "blob:now", revokeObjectURL: revoke });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    downloadText("a.json", "{}", "application/json", 0);

    expect(revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(0);
    expect(revoke).toHaveBeenCalledWith("blob:now");
  });

  it("propagates a failure to create the object URL", () => {
    Object.assign(URL, { createObjectURL: () => { throw new Error("no blobs"); }, revokeObjectURL: vi.fn() });
    expect(() => downloadText("a.json", "{}", "application/json")).toThrow("no blobs");
  });
});
