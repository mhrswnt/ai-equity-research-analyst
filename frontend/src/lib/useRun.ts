"use client";
import { useCallback, useState } from "react";
import { ApiError } from "./api";

/** Wraps an async API call with loading/error/result state. */
export function useRun<A extends unknown[], T>(fn: (...args: A) => Promise<T>) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [result, setResult] = useState<T | null>(null);
  const run = useCallback(async (...args: A) => {
    setLoading(true);
    setError(null);
    try {
      const r = await fn(...args);
      setResult(r);
      return r;
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      return null;
    } finally {
      setLoading(false);
    }
  }, [fn]);
  return { run, loading, error, result, setResult, setError };
}
