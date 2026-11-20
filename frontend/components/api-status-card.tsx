"use client";

import { useEffect, useState } from "react";

import { ApiError, getReadiness, type ReadinessStatus } from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "ready"; status: ReadinessStatus }
  | { kind: "error"; message: string };

export function ApiStatusCard() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getReadiness(controller.signal).then(
      (status) => setState({ kind: "ready", status }),
      (error: unknown) =>
        setState({
          kind: "error",
          message: error instanceof ApiError ? error.message : "API is unreachable.",
        }),
    );
    return () => controller.abort();
  }, []);

  if (state.kind === "loading") {
    return (
      <p role="status" className="rounded-xl bg-black/5 px-4 py-3 text-sm">
        Checking API status…
      </p>
    );
  }
  if (state.kind === "error") {
    return (
      <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-900">
        API unreachable: {state.message} Is the backend running?
      </p>
    );
  }
  return (
    <dl className="rounded-xl bg-black/5 px-4 py-3 text-sm">
      <div className="flex justify-between gap-4">
        <dt>API</dt>
        <dd>{state.status.ready ? "ready" : "not ready"}</dd>
      </div>
      {Object.entries(state.status.components).map(([name, value]) => (
        <div key={name} className="flex justify-between gap-4">
          <dt className="capitalize">{name}</dt>
          <dd>{value}</dd>
        </div>
      ))}
      <div className="flex justify-between gap-4 text-xs opacity-70">
        <dt>Version</dt>
        <dd>{state.status.version}</dd>
      </div>
    </dl>
  );
}
