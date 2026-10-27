/**
 * A component whose code is in a separate chunk (a dynamic `import()`), so
 * the entry chunk holds only what the first screen needs.
 *
 * Unlike a bare `React.lazy`, a component whose chunk has already arrived
 * (after `preload()`) renders at once, with no Suspense fallback, not even
 * for a frame. Before that it renders through `React.lazy`: it suspends and
 * the nearest `<Suspense>` shows its fallback until the chunk arrives. Each
 * mounted instance keeps the path it started with, so its state survives
 * the chunk's arrival. A chunk that fails to load renders `failed` (a
 * readable message) instead of throwing to the error boundary.
 */
import { createElement, lazy, useState, type ComponentType, type ReactElement } from "react";

export type Preloadable<P> = ((props: P) => ReactElement) & {
  /** Start loading the chunk (once); resolves when the component renders without suspending. */
  preload: () => Promise<unknown>;
};

export function preloadable<P extends object>(
  load: () => Promise<ComponentType<P>>,
  failed: (message: string) => ComponentType<P>,
  name: string,
): Preloadable<P> {
  let promise: Promise<ComponentType<P>> | null = null;
  let loaded: ComponentType<P> | null = null;
  const start = (): Promise<ComponentType<P>> => {
    if (!promise) {
      promise = load()
        .catch((error: unknown) => failed(error instanceof Error ? error.message : String(error)))
        .then((component) => {
          loaded = component;
          return component;
        });
    }
    return promise;
  };
  const Suspending = lazy(() => start().then((component) => ({ default: component })));
  const Component = (props: P): ReactElement => {
    // Decided once per instance: switching paths later would remount it.
    const [ready] = useState(() => loaded);
    return ready ? createElement(ready, props) : createElement(Suspending, props);
  };
  Component.displayName = name;
  Component.preload = start;
  return Component;
}
