import { useState } from "react";
import type { Bundle } from "../types";
import type { ArtifactIdentity } from "../lib/artifactIdentity";
import { investigationMarkdown, investigationPacket, type InvestigationTarget } from "../lib/investigationPacket";

export function InvestigationPacket({ bundle, identity, target, turn }: {
  bundle: Bundle; identity: ArtifactIdentity | null; target: InvestigationTarget | null; turn: number;
}) {
  const [status, setStatus] = useState("");
  const download = (format: "json" | "md") => {
    if (!target) return;
    try {
      const packet = investigationPacket(bundle, identity, target, turn);
      const text = format === "json" ? JSON.stringify(packet, null, 2) : investigationMarkdown(packet);
      const url = URL.createObjectURL(new Blob([text], { type: format === "json" ? "application/json" : "text/markdown" }));
      const link = document.createElement("a");
      link.href = url; link.download = `chronicler-investigation-turn-${turn}.${format}`; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setStatus("Investigation exported with exact values and source references. Private bookmark notes are excluded.");
    } catch (error) { setStatus(error instanceof Error ? error.message : "Investigation export failed. Your world and notes are kept."); }
  };
  return <section aria-label="Share investigation">
    <h3>Share this investigation</h3>
    <p>Selected entity and snapshot values, a bounded window of recorded event references, file identity and limitations. No raw world, private notes or machine paths.</p>
    {!target && <p>Select an unambiguous region or civilization first.</p>}
    <button type="button" disabled={!target} onClick={() => download("json")}>Export investigation JSON</button>
    <button type="button" disabled={!target} onClick={() => download("md")}>Export investigation Markdown</button>
    <p role="status">{status}</p>
  </section>;
}
