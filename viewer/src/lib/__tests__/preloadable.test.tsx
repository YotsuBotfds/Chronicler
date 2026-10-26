import { Suspense, useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { preloadable } from "../preloadable";

afterEach(cleanup);

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function Greeting({ name }: { name: string }) {
  return <p>Hello {name}</p>;
}

const failed = (message: string) => function Failed() {
  return <p role="alert">Could not load: {message}</p>;
};

function inSuspense(element: React.ReactNode) {
  return <Suspense fallback={<p role="status">Loading...</p>}>{element}</Suspense>;
}

describe("preloadable", () => {
  it("shows the fallback until the chunk arrives, then the component", async () => {
    const chunk = deferred<typeof Greeting>();
    const Lazy = preloadable(() => chunk.promise, failed, "Lazy");
    render(inSuspense(<Lazy name="Aria" />));
    expect(screen.getByRole("status")).toHaveTextContent("Loading...");
    await act(async () => {
      chunk.resolve(Greeting);
      await Lazy.preload();
    });
    expect(screen.getByText("Hello Aria")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders at once, without a fallback, once preloaded", async () => {
    let loads = 0;
    const Lazy = preloadable(async () => {
      loads += 1;
      return Greeting;
    }, failed, "Lazy");
    await Lazy.preload();
    render(inSuspense(<Lazy name="Bel" />));
    // Synchronously after the first render: no Suspense fallback at all.
    expect(screen.getByText("Hello Bel")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    await Lazy.preload();
    expect(loads).toBe(1);
  });

  it("keeps an instance's state when it re-renders after its chunk arrived", async () => {
    function Counter({ label }: { label: string }) {
      const [count, setCount] = useState(0);
      return <button type="button" onClick={() => setCount(count + 1)}>{label} {count}</button>;
    }
    const chunk = deferred<typeof Counter>();
    const Lazy = preloadable(() => chunk.promise, failed, "Lazy");
    const { rerender } = render(inSuspense(<Lazy label="Count" />));
    await act(async () => {
      chunk.resolve(Counter);
      await Lazy.preload();
    });
    fireEvent.click(screen.getByRole("button", { name: "Count 0" }));
    rerender(inSuspense(<Lazy label="Total" />));
    expect(screen.getByRole("button", { name: "Total 1" })).toBeInTheDocument();
  });

  it("renders a readable message when the chunk fails to load", async () => {
    const chunk = deferred<typeof Greeting>();
    const Lazy = preloadable(() => chunk.promise, failed, "Lazy");
    render(inSuspense(<Lazy name="Cor" />));
    await act(async () => {
      chunk.reject(new Error("Failed to fetch dynamically imported module"));
      await Lazy.preload();
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load: Failed to fetch dynamically imported module");
  });
});
