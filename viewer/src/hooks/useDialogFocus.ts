import { useEffect, useEffectEvent, type RefObject } from "react";

/** Modal keyboard containment; closing restores the prior connected focus target. */
export function useDialogFocus(ref: RefObject<HTMLElement | null>, enabled: boolean, onDismiss?: () => void) {
  const dismiss = useEffectEvent(() => onDismiss?.());
  useEffect(() => {
    const dialog = ref.current;
    if (!enabled || !dialog) return;
    const previous = document.activeElement;
    const focusable = () => [...dialog.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"], summary',
    )].filter((node) => node.getClientRects().length > 0 && !node.closest('[hidden], [inert], fieldset:disabled'));
    dialog.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); dismiss(); }
      if (event.key !== "Tab") return;
      const nodes = focusable(), first = nodes[0], last = nodes.at(-1);
      if (!first || !last) { event.preventDefault(); dialog.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    };
    const contain = (event: FocusEvent) => {
      if (event.target instanceof Node && !dialog.contains(event.target)) dialog.focus();
    };
    dialog.addEventListener("keydown", keydown);
    document.addEventListener("focusin", contain);
    return () => {
      dialog.removeEventListener("keydown", keydown);
      document.removeEventListener("focusin", contain);
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
      else if (previous instanceof SVGElement && previous.isConnected) previous.focus();
    };
  }, [enabled, ref]);
}
