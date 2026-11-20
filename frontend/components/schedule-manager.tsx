"use client";

import { useCallback, useEffect, useState } from "react";

import { useSpace } from "@/components/space-provider";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import {
  cancelScheduledEvent,
  createScheduledEvent,
  listSchedule,
  type ScheduledEvent,
} from "@/lib/studio";

const KINDS = [
  { value: "reveal", label: "Reveal", hint: "Publish a scheduled space at a date." },
  { value: "reminder", label: "Reminder", hint: "Email the host before a date." },
  { value: "capsule", label: "Time capsule", hint: 'Payload: {"contribution_ids": [...]}.' },
];

export function ScheduleManager({ spaceId }: { spaceId: string }) {
  const { space, token } = useSpace();
  const [events, setEvents] = useState<ScheduledEvent[]>([]);
  const [kind, setKind] = useState("reveal");
  const [runAt, setRunAt] = useState("");
  const [payload, setPayload] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setEvents(await listSchedule(spaceId, token));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not load the schedule.");
    }
  }, [spaceId, token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!space.my_permissions.includes("edit_space")) {
    return null;
  }

  async function create() {
    setError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(payload || "{}") as Record<string, unknown>;
    } catch {
      setError("Payload must be valid JSON.");
      return;
    }
    try {
      await createScheduledEvent(spaceId, { kind, run_at: new Date(runAt).toISOString(), payload: parsed }, token);
      setRunAt("");
      await refresh();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not schedule.");
    }
  }

  return (
    <section aria-label="Scheduled reveals and reminders" className="flex flex-col gap-3">
      <h2 className="text-xl font-bold">Schedule</h2>
      <p className="text-sm opacity-70">
        Times run in the space timezone. Nothing reveals before its moment.
      </p>
      {events.length === 0 && <p className="text-sm opacity-60">Nothing scheduled.</p>}
      {events.map((event) => (
        <div key={event.id} className="flex items-center justify-between gap-3 rounded-xl bg-black/5 px-4 py-2 text-sm">
          <span>
            {event.kind} · {new Date(event.run_at).toLocaleString()} · <strong>{event.status}</strong>
          </span>
          {event.status === "scheduled" && (
            <button
              type="button"
              onClick={() => cancelScheduledEvent(event.id, token).then(refresh)}
              className="min-h-[44px] rounded-full bg-white px-3 text-sm font-medium"
            >
              Cancel
            </button>
          )}
        </div>
      ))}
      <div className="flex flex-col gap-2 rounded-2xl border border-black/10 p-4">
        <div className="flex gap-2">
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
            aria-label="Event kind"
            className="min-h-[44px] rounded-xl border border-black/15 bg-white/80 px-3 text-sm"
          >
            {KINDS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <input
            type="datetime-local"
            value={runAt}
            onChange={(event) => setRunAt(event.target.value)}
            aria-label="Run at"
            className="min-h-[44px] flex-1 rounded-xl border border-black/15 bg-white/80 px-3 text-sm"
          />
        </div>
        <p className="text-xs opacity-60">{KINDS.find((option) => option.value === kind)?.hint}</p>
        <textarea
          value={payload}
          onChange={(event) => setPayload(event.target.value)}
          rows={2}
          spellCheck={false}
          aria-label="Payload JSON"
          className="rounded-xl border border-black/15 bg-white/80 px-3 py-2 font-mono text-xs"
        />
        <div>
          <Button type="button" onClick={create} disabled={!runAt}>
            Schedule
          </Button>
        </div>
      </div>
      {error && (
        <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-900">
          {error}
        </p>
      )}
    </section>
  );
}
