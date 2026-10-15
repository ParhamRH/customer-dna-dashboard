"use client";
import * as React from "react";

/**
 * State that re-initialises whenever any value in `deps` changes (compared with Object.is) —
 * e.g. a form that must start fresh each time its dialog opens for a different record.
 * Uses React's "adjust state while rendering" pattern instead of an effect, so there is no
 * extra render with stale values.
 */
export function useResetState<T>(deps: readonly unknown[], init: () => T): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = React.useState(init);
  const [prev, setPrev] = React.useState<readonly unknown[]>(deps);
  if (prev.length !== deps.length || prev.some((d, i) => !Object.is(d, deps[i]))) {
    setPrev(deps);
    setState(init());
  }
  return [state, setState];
}

/** Run `onChange` (during render) when `value` changes; for resetting several related states at once. */
export function useOnChange(value: unknown, onChange: () => void) {
  const [prev, setPrev] = React.useState(value);
  if (!Object.is(prev, value)) {
    setPrev(value);
    onChange();
  }
}

const listeners = new Set<() => void>();
function emit() {
  listeners.forEach((l) => l());
}
function subscribe(l: () => void) {
  listeners.add(l);
  const onStorage = (e: StorageEvent) => e.key && l();
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(l);
    window.removeEventListener("storage", onStorage);
  };
}
function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // storage blocked (private mode, sandboxed preview)
  }
}

/**
 * A per-browser preference kept in localStorage (view mode, theme). Renders `fallback` on the
 * server and until hydration, then the stored value; never throws when storage is unavailable.
 */
export function useStoredPreference<T extends string>(key: string, fallback: T, allowed?: readonly T[]): [T, (v: T) => void] {
  const raw = React.useSyncExternalStore(
    subscribe,
    () => read(key),
    () => null,
  );
  const value = raw && (!allowed || (allowed as readonly string[]).includes(raw)) ? (raw as T) : fallback;
  const set = React.useCallback(
    (v: T) => {
      try {
        window.localStorage.setItem(key, v);
      } catch {
        /* storage unavailable — keep working without persistence */
      }
      emit();
    },
    [key],
  );
  return [value, set];
}
