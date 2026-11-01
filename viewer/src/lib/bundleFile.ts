/**
 * An uploaded bundle file, from its bytes to the bundle the viewer reads.
 *
 * The same steps run in the decode worker (`bundleDecode.worker.ts`, for
 * large files) and on the main thread (small files, and wherever a worker
 * cannot run): BOM-aware text decoding, JSON parsing, the loader's checks
 * and the version-6 history expansion (`bundleCodec`, which throws
 * `BundleDecodeError` for a malformed patch and becomes the loader's
 * `INVALID_HISTORY_DELTA` message), and the hash of the original bytes.
 * Nothing here touches React or the DOM.
 */
import type { Bundle } from "../types";
import { identifyArtifact, type ArtifactIdentity } from "./artifactIdentity";
import { formatBundleLoaderDiagnostics, parseBundleJsonPayload } from "./bundleLoader";
import { checkpointNotice } from "./checkpointFile";
import { validateBundleStructure, validateViewableBundle } from "./bundleValidation";

export interface DecodedBundleFile {
  bundle: Bundle | null;
  error: string | null;
  identity: ArtifactIdentity | null;
}

/** Historical JSON decoding contract. File uploads additionally check whether
 * the decoded world has the required display fields in parseBundleBytes. */
export function parseBundle(jsonString: string): {
  bundle: Bundle | null;
  error: string | null;
} {
  let result: ReturnType<typeof parseBundleJsonPayload>;
  try {
    result = parseBundleJsonPayload(jsonString);
  } catch (error) {
    return { bundle: null, error: `Could not read bundle: ${error instanceof Error ? error.message : String(error)}` };
  }
  if (result.kind === "legacy") {
    const invalid = validateBundleStructure(result.bundle as unknown as Record<string, unknown>);
    if (invalid) return { bundle: null, error: `Invalid bundle: ${invalid}. Open a complete chronicle_bundle.json export.` };
    return { bundle: result.bundle, error: null };
  }

  return {
    bundle: null,
    error: formatBundleLoaderDiagnostics(result.diagnostics),
  };
}

/** The file's text, as `readAsText` would decode it (a UTF-16 byte order mark is honoured). */
export function decodeBundleText(bytes: ArrayBuffer): string {
  const prefix = new Uint8Array(bytes, 0, Math.min(2, bytes.byteLength));
  const encoding = prefix[0] === 0xff && prefix[1] === 0xfe ? "utf-16le"
    : prefix[0] === 0xfe && prefix[1] === 0xff ? "utf-16be" : "utf-8";
  return new TextDecoder(encoding).decode(bytes);
}

/** The bundle in a file's bytes, the loader's error, and (for a bundle) the bytes' identity. */
export async function decodeBundleBytes(name: string, bytes: ArrayBuffer): Promise<DecodedBundleFile> {
  const result = parseBundleBytes(bytes);
  const identity = result.bundle ? await identifyArtifact(name, bytes) : null;
  return { bundle: result.bundle, error: result.error, identity };
}

/** Recognize the binary envelope before any text or JSON decoding. */
export function parseBundleBytes(bytes: ArrayBuffer): ReturnType<typeof parseBundle> {
  const notice = checkpointNotice(bytes);
  if (notice) return { bundle: null, error: notice };
  const parsed = parseBundle(decodeBundleText(bytes));
  if (parsed.bundle) {
    const invalid = validateViewableBundle(parsed.bundle as unknown as Record<string, unknown>);
    if (invalid) return { bundle: null, error: `Incomplete or invalid viewer bundle: ${invalid}. Open a complete chronicle_bundle.json export.` };
  }
  return parsed;
}
