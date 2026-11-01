import { isRecord } from "./bundleValidation";

// Exact run_checkpoint.py envelope. Only its JSON header is inspected here.
const MAGIC = new Uint8Array([0x89, ...new TextEncoder().encode("CHRONICLER-CKPT\r\n"), 0x1a, 0x0a]);

export function checkpointNotice(bytes: ArrayBuffer): string | null {
  const data = new Uint8Array(bytes);
  if (data.length === 0 || !MAGIC.subarray(0, Math.min(data.length, MAGIC.length))
    .every((value, index) => data[index] === value)) return null;
  const prefix = "Exact run checkpoint detected";
  const cli = "Open chronicle_bundle.json to view recorded history. Resume a trusted checkpoint with the CLI: " +
    "python -m chronicler.main --resume /path/to/checkpoint.ckpt --live --simulate-only. " +
    "Exact continuation requires the matching source, native build and environment. " +
    "The browser never deserializes checkpoint sections or verifies their integrity.";
  const corrupt = `${prefix}, but its header or section layout is incomplete or corrupt. ${cli}`;
  const start = MAGIC.length + 4;
  if (data.length < start) return corrupt;
  const length = new DataView(bytes).getUint32(MAGIC.length, true);
  if (length > data.length - start || length === 0) return corrupt;
  let header: unknown;
  try {
    header = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(data.subarray(start, start + length)));
  } catch { return corrupt; }
  if (!isRecord(header) || header.format !== "chronicler-run-checkpoint") return corrupt;
  if (header.version !== 1) return `${prefix}: unsupported format version ${String(header.version)}. ${cli}`;
  if (!Array.isArray(header.sections) || header.sections.length === 0) return corrupt;
  let offset = 0;
  for (const section of header.sections) {
    if (!isRecord(section) || section.offset !== offset || !Number.isSafeInteger(section.length)
      || (section.length as number) < 0) return corrupt;
    offset += section.length as number;
  }
  if (offset !== data.length - start - length) return corrupt;
  const name = isRecord(header.world) && typeof header.world.name === "string" ? `: ${header.world.name}` : "";
  const seed = typeof header.seed === "number" ? `, seed ${header.seed}` : "";
  const turn = typeof header.turn === "number" ? `, saved turn ${header.turn}` : "";
  return `${prefix}${name}${seed}${turn} (header only; not a viewable bundle). ${cli}`;
}
