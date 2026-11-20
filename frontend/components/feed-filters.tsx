"use client";

import type { FeedParams } from "@/lib/spaces";

export interface FilterValues {
  q: string;
  kind: string;
  sort: string;
}

const KIND_OPTIONS = [
  { value: "", label: "Everything" },
  { value: "message", label: "Messages" },
  { value: "story", label: "Stories" },
  { value: "media", label: "Photos & video" },
  { value: "audio", label: "Voice notes" },
];

const SORT_OPTIONS = [
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
  { value: "-taken_at", label: "Memory date ↓" },
  { value: "taken_at", label: "Memory date ↑" },
];

export function FeedFilters({
  values,
  onChange,
}: {
  values: FilterValues;
  onChange: (values: FilterValues) => void;
}) {
  return (
    <form
      role="search"
      aria-label="Filter memories"
      className="flex flex-col gap-2 sm:flex-row"
      onSubmit={(event) => event.preventDefault()}
    >
      <input
        type="search"
        value={values.q}
        onChange={(event) => onChange({ ...values, q: event.target.value })}
        placeholder="Search memories…"
        aria-label="Search memories"
        className="min-h-[44px] flex-1 rounded-xl border border-black/15 bg-white/80 px-4 text-[15px]"
      />
      <select
        value={values.kind}
        onChange={(event) => onChange({ ...values, kind: event.target.value })}
        aria-label="Filter by type"
        className="min-h-[44px] rounded-xl border border-black/15 bg-white/80 px-3 text-sm"
      >
        {KIND_OPTIONS.map((option) => (
          <option key={option.label} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <select
        value={values.sort}
        onChange={(event) => onChange({ ...values, sort: event.target.value })}
        aria-label="Sort order"
        className="min-h-[44px] rounded-xl border border-black/15 bg-white/80 px-3 text-sm"
      >
        {SORT_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </form>
  );
}

export function toFeedParams(values: FilterValues): FeedParams {
  return {
    q: values.q.trim() || undefined,
    kind: values.kind || undefined,
    sort: values.sort,
    limit: 20,
  };
}
