import { useState, useCallback } from "react";
import type { Bundle } from "../types";

const REQUIRED_KEYS: (keyof Bundle)[] = [
  "world_state",
  "history",
  "events_timeline",
  "named_events",
  "chronicle_entries",
  "era_reflections",
  "metadata",
];

export function parseBundle(jsonString: string): {
  bundle: Bundle | null;
  error: string | null;
} {
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonString);
  } catch {
    return { bundle: null, error: "Invalid JSON: could not parse file" };
  }

  if (typeof parsed !== "object" || parsed === null) {
    return { bundle: null, error: "Invalid JSON: expected an object" };
  }

  const obj = parsed as Record<string, unknown>;
  const missing = REQUIRED_KEYS.filter((k) => !(k in obj));
  if (missing.length > 0) {
    return {
      bundle: null,
      error: `Missing required keys: ${missing.join(", ")}`,
    };
  }

  return { bundle: obj as unknown as Bundle, error: null };
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
