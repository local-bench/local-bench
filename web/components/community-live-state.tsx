"use client";

import { useEffect, useState } from "react";
import type { CommunityBoardRow } from "@/lib/community-data";
import { parseCommunityLiveBoard, reconcileCommunityRows } from "@/lib/community-live";
import {
  EMPTY_FAMILY_RESOLUTION_CONTEXT,
  type FamilyResolutionContext,
} from "@/lib/family-resolution";

export type LiveCommunityState =
  | { readonly kind: "loading"; readonly rows: readonly CommunityBoardRow[] }
  | { readonly kind: "snapshot"; readonly rows: readonly CommunityBoardRow[] }
  | {
    readonly droppedRows: number;
    readonly generatedAt: string;
    readonly kind: "live";
    readonly rows: readonly CommunityBoardRow[];
  };

export function useLiveCommunityRows(
  bakedRows: readonly CommunityBoardRow[],
  enabled = true,
  resolutionContext: FamilyResolutionContext = EMPTY_FAMILY_RESOLUTION_CONTEXT,
): LiveCommunityState {
  const [state, setState] = useState<LiveCommunityState>({ kind: "loading", rows: bakedRows });
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    async function load(): Promise<void> {
      try {
        const response = await fetch("/api/board/community.json", {
          headers: { accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) {
          setState({ kind: "snapshot", rows: bakedRows });
          return;
        }
        const parsed = parseCommunityLiveBoard(await response.json());
        if (parsed === null) {
          setState({ kind: "snapshot", rows: bakedRows });
          return;
        }
        setState({
          droppedRows: parsed.droppedRows,
          generatedAt: parsed.generatedAt,
          kind: "live",
          rows: reconcileCommunityRows(bakedRows, parsed.rows, resolutionContext),
        });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState({ kind: "snapshot", rows: bakedRows });
      }
    }
    void load();
    return () => controller.abort();
  }, [bakedRows, enabled, resolutionContext]);
  return state;
}

export function CommunityFreshness({
  communityUnavailable = false,
  now,
  state,
}: {
  readonly communityUnavailable?: boolean;
  readonly now?: number;
  readonly state: LiveCommunityState;
}) {
  const [clock, setClock] = useState(() => now ?? Date.now());
  useEffect(() => {
    if (now !== undefined || state.kind !== "live") return;
    const timer = window.setInterval(() => setClock(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [now, state.kind]);
  if (state.kind === "loading") {
    return <p aria-hidden className="h-4 font-mono text-xs text-bench-muted" />;
  }
  if (state.kind === "snapshot") {
    return (
      <p className="font-mono text-xs text-bench-muted">
        showing last published snapshot{communityUnavailable ? " · live data unavailable" : ""}
      </p>
    );
  }
  const ageSeconds = Math.max(0, Math.floor((clock - Date.parse(state.generatedAt)) / 1_000));
  const heldBack = state.droppedRows === 0 ? "" : ` · ${state.droppedRows} rows held back`;
  return <p className="font-mono text-xs text-bench-muted">live · updated {ageSeconds}s ago{heldBack}</p>;
}
