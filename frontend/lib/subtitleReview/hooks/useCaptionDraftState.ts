"use client";

import { useCallback, useRef, useState, type SetStateAction } from "react";

// Network replies need the latest keystroke, including updates still queued for
// React's next render. All draft writers use this same synchronous mirror.
export function useCaptionDraftState<T>(initial: T) {
  const [value, render] = useState(initial);
  const latest = useRef(initial);
  const setValue = useCallback((update: SetStateAction<T>) => {
    const next = typeof update === "function" ? (update as (current: T) => T)(latest.current) : update;
    latest.current = next;
    render(next);
  }, []);
  return [value, setValue, latest] as const;
}
