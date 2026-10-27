import { useState, useCallback, useEffect, useRef } from "react";
import type { Bundle } from "../types";
import type { ArtifactIdentity } from "../lib/artifactIdentity";
import { decodeInWorker, type DecodeJob, type DecodeReply } from "../lib/bundleDecode";
import { decodeBundleBytes, parseBundle } from "../lib/bundleFile";

export { parseBundle };

/**
 * The uploaded bundle. A large file is read and decoded in a worker
 * (lib/bundleDecode), a small one, or any file where no worker can run, on
 * the main thread; both give the same bundle, identity and messages.
 */
export function useBundle() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [artifactIdentity, setArtifactIdentity] = useState<ArtifactIdentity | null>(null);
  const loadSequence = useRef(0);
  const job = useRef<DecodeJob | null>(null);

  useEffect(() => () => job.current?.cancel(), []);

  const loadFromFile = useCallback((file: File) => {
    const sequence = ++loadSequence.current;
    const current = () => sequence === loadSequence.current;
    job.current?.cancel();
    job.current = null;
    setLoading(true);
    setError(null);

    const apply = (reply: DecodeReply) => {
      if (!current()) return;
      if (reply.kind === "decoded") {
        setBundle(reply.result.bundle);
        setArtifactIdentity(reply.result.identity);
        setError(reply.result.error);
      } else if (reply.kind === "read-error") {
        setError("Failed to read file");
      } else {
        setBundle(null);
        setArtifactIdentity(null);
        setError(`Could not read bundle: ${reply.message}`);
      }
      setLoading(false);
    };

    const readOnMainThread = () => {
      const reader = new FileReader();
      reader.onload = async (e) => {
        // Whatever fails while decoding, the loading state ends and the error shows.
        try {
          // Preserve readAsText's BOM-aware decoding while retaining original bytes.
          const bytes = e.target?.result as ArrayBuffer;
          const result = await decodeBundleBytes(file.name, bytes);
          if (!current()) return;
          setBundle(result.bundle);
          setArtifactIdentity(result.identity);
          setError(result.error);
        } catch (error) {
          if (!current()) return;
          setBundle(null);
          setArtifactIdentity(null);
          setError(`Could not read bundle: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
          if (current()) {
            setLoading(false);
          }
        }
      };
      reader.onerror = () => {
        if (!current()) return;
        setError("Failed to read file");
        setLoading(false);
      };
      reader.readAsArrayBuffer(file);
    };

    const started = decodeInWorker(file);
    if (!started) {
      readOnMainThread();
      return;
    }
    job.current = started;
    started.reply.then(apply, () => {
      // The worker could not do it (it failed to start or crashed): decode here.
      if (current()) {
        job.current = null;
        readOnMainThread();
      }
    });
  }, []);

  return { bundle, artifactIdentity, error, loading, loadFromFile };
}
