/**
 * Placeholder while a lazy panel's chunk loads (lazyPanels.ts): a polite
 * status line in the panel's place, so the layout does not jump when the
 * panel arrives.
 */
export function PanelLoading({ label, className = "" }: { label: string; className?: string }) {
  return (
    <div
      className={`phase75-panel-loading ${className}`.trim()}
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-lazy-fallback=""
    >
      Loading {label}...
    </div>
  );
}
