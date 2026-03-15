import { useState, useCallback } from "react";
import type { BatchConfig, BatchReport } from "../types";

export type BatchState = "idle" | "running" | "complete" | "cancelled" | "error";

export interface BatchConnectionState {
  batchState: BatchState;
  report: BatchReport | null;
  progress: { completed: number; total: number; currentSeed: number } | null;
  error: string | null;
  startBatch: (config: BatchConfig) => void;
  cancelBatch: () => void;
  loadReportFromFile: (report: BatchReport) => void;
  reset: () => void;
  handleMessage: (msg: Record<string, unknown>) => void;
}

export function useBatchConnection(wsRef: React.RefObject<WebSocket | null>): BatchConnectionState {
  const [batchState, setBatchState] = useState<BatchState>("idle");
  const [report, setReport] = useState<BatchReport | null>(null);
  const [progress, setProgress] = useState<{ completed: number; total: number; currentSeed: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleMessage = useCallback((msg: Record<string, unknown>) => {
    switch (msg.type) {
      case "batch_progress":
        setProgress({
          completed: msg.completed as number,
          total: msg.total as number,
          currentSeed: msg.current_seed as number,
        });
        break;
      case "batch_complete":
        setBatchState("complete");
        setReport(msg.report as BatchReport);
        setProgress(null);
        break;
      case "batch_cancelled":
        setBatchState("cancelled");
        setProgress(null);
        break;
      case "batch_error":
        setBatchState("error");
        setError(msg.message as string);
        setProgress(null);
        break;
      case "batch_report_loaded":
        setReport(msg.report as BatchReport);
        break;
    }
  }, []);

  const startBatch = useCallback((config: BatchConfig) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setBatchState("running");
      setError(null);
      setReport(null);
      setProgress({ completed: 0, total: config.seed_count, currentSeed: config.seed_start });
      wsRef.current.send(JSON.stringify({ type: "batch_start", config }));
    }
  }, [wsRef]);

  const cancelBatch = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "batch_cancel" }));
    }
  }, [wsRef]);

  const loadReportFromFile = useCallback((r: BatchReport) => {
    setReport(r);
  }, []);

  const reset = useCallback(() => {
    setBatchState("idle");
    setReport(null);
    setProgress(null);
    setError(null);
  }, []);

  return {
    batchState, report, progress, error,
    startBatch, cancelBatch, loadReportFromFile, reset, handleMessage,
  };
}
