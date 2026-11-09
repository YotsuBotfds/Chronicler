import type { ReactNode } from "react";

/**
 * A systems panel section: `label` names it for assistive technology and is
 * the heading unless `title` is given. `note` is the first systems note under
 * the heading. When `emptyText` is given it replaces the note and children.
 */
export function SystemSection({ label, title, note, emptyText, children }: {
  label: string; title?: ReactNode; note?: ReactNode; emptyText?: ReactNode; children?: ReactNode;
}) {
  return <section className="systems-section" aria-label={label}>
    <h3>{title ?? label}</h3>
    {emptyText !== undefined ? <p className="systems-note">{emptyText}</p> : <>
      {note !== undefined ? <p className="systems-note">{note}</p> : null}
      {children}
    </>}
  </section>;
}
