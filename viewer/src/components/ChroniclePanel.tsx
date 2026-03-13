import { useEffect, useRef } from "react";

interface ChroniclePanelProps {
  chronicleEntries: Record<string, string>;
  eraReflections: Record<string, string>;
  currentTurn: number;
  maxTurn: number;
}

export function ChroniclePanel({
  chronicleEntries,
  eraReflections,
  currentTurn,
  maxTurn,
}: ChroniclePanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const turnRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  useEffect(() => {
    const el = turnRefs.current.get(currentTurn);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [currentTurn]);

  const turns = Array.from({ length: maxTurn }, (_, i) => i + 1);

  return (
    <div ref={containerRef} className="overflow-y-auto h-full p-4 space-y-4">
      {turns.map((turn) => {
        const entry = chronicleEntries[String(turn)];
        const reflection = eraReflections[String(turn)];
        if (!entry && !reflection) return null;

        return (
          <div
            key={turn}
            ref={(el) => {
              if (el) turnRefs.current.set(turn, el);
            }}
            className={`${
              turn === currentTurn
                ? "border-l-2 border-blue-400 pl-3"
                : "pl-4 opacity-60"
            }`}
          >
            {reflection && (
              <div className="mb-3 p-3 bg-gray-800 rounded border border-gray-600 text-sm text-gray-300 whitespace-pre-wrap">
                {reflection}
              </div>
            )}
            {entry && (
              <div>
                <span className="text-xs text-gray-500 font-mono">
                  Turn {turn}
                </span>
                <p className="text-gray-200 leading-relaxed whitespace-pre-wrap">
                  {entry}
                </p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
