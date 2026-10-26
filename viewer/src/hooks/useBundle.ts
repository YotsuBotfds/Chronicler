import { useState, useCallback, useRef } from "react";
import type { Bundle } from "../types";
import { formatBundleLoaderDiagnostics, parseBundleJsonPayload } from "../lib/bundleLoader";
import { identifyArtifact, type ArtifactIdentity } from "../lib/artifactIdentity";

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
    return { bundle: result.bundle, error: null };
  }

  return {
    bundle: null,
    error: formatBundleLoaderDiagnostics(result.diagnostics),
  };
}

export function useBundle() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [artifactIdentity, setArtifactIdentity] = useState<ArtifactIdentity | null>(null);
  const loadSequence = useRef(0);

  const loadFromFile = useCallback((file: File) => {
    const sequence = ++loadSequence.current;
    setLoading(true);
    setError(null);
    const reader = new FileReader();
    reader.onload = async (e) => {
      // Whatever fails while decoding, the loading state ends and the error shows.
      try {
        const bytes = e.target?.result as ArrayBuffer;
        // Preserve readAsText's BOM-aware decoding while retaining original bytes.
        const prefix = new Uint8Array(bytes, 0, Math.min(2, bytes.byteLength));
        const encoding = prefix[0] === 0xff && prefix[1] === 0xfe ? "utf-16le"
          : prefix[0] === 0xfe && prefix[1] === 0xff ? "utf-16be" : "utf-8";
        const text = new TextDecoder(encoding).decode(bytes);
        const result = parseBundle(text);
        const identity = result.bundle ? await identifyArtifact(file.name, bytes) : null;
        if (sequence !== loadSequence.current) return;
        setBundle(result.bundle);
        setArtifactIdentity(identity);
        setError(result.error);
      } catch (error) {
        if (sequence !== loadSequence.current) return;
        setBundle(null);
        setArtifactIdentity(null);
        setError(`Could not read bundle: ${error instanceof Error ? error.message : String(error)}`);
      } finally {
        if (sequence === loadSequence.current) {
          setLoading(false);
        }
      }
    };
    reader.onerror = () => {
      if (sequence !== loadSequence.current) return;
      setError("Failed to read file");
      setLoading(false);
    };
    reader.readAsArrayBuffer(file);
  }, []);

  return { bundle, artifactIdentity, error, loading, loadFromFile };
}
