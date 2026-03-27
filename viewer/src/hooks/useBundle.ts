import { useState, useCallback } from "react";
import type { Bundle } from "../types";
import { formatBundleLoaderDiagnostics, parseBundleJsonPayload } from "../lib/bundleLoader";

export function parseBundle(jsonString: string): {
  bundle: Bundle | null;
  error: string | null;
} {
  const result = parseBundleJsonPayload(jsonString);
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

  const loadFromFile = useCallback((file: File) => {
    setLoading(true);
    setError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const result = parseBundle(text);
      setBundle(result.bundle);
      setError(result.error);
      setLoading(false);
    };
    reader.onerror = () => {
      setError("Failed to read file");
      setLoading(false);
    };
    reader.readAsText(file);
  }, []);

  return { bundle, error, loading, loadFromFile };
}
