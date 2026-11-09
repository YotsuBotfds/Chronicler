import type { ReactNode } from "react";

/** A labelled systems table inside its scrolling wrapper (`systems-table-wrap`). */
export function SystemTable({ label, className, children }: {
  label: string; className?: string; children: ReactNode;
}) {
  return <div className="systems-table-wrap">
    <table className={className ? `systems-table ${className}` : "systems-table"} aria-label={label}>{children}</table>
  </div>;
}
