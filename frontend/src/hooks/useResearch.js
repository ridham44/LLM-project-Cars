import { useCallback, useRef, useState } from "react";
import { pollResearch, submitResearch } from "../services/research";
import { isLiveStatus } from "../constants";

const TERMINAL_STATUSES = new Set(["completed", "error"]);

const initialState = {
  phase: "idle",
  report: null,
  error: null,
  // Identifies the Recent Research row this view belongs to. It travels with
  // the view (including through the back stack) so progress updates always
  // land on the right row, whichever run is currently on screen.
  trackingKey: null,
};

// Owns the research request lifecycle: submit -> (optionally poll) -> settle.
// `phase` mirrors the backend's reported status (planning, retrieving,
// analyzing, verifying, synthesizing, completed, error) so ResearchProgress can
// render real progress instead of a generic spinner.
//
// It also owns a small view stack. Opening a recent-research item or an
// example REPLACES what's on screen, and on this hardware the thing being
// replaced is often a run that has been grinding for minutes - so every
// replacement pushes the current view and `goBack()` restores it. Because
// POST /research hands back a job id and the backend worker thread keeps
// running whether or not anyone is polling (backend/jobs.py), going back to
// an unfinished run resumes its live progress rather than freezing on the
// last frame that happened to be on screen when it was left.
export function useResearch() {
  const [state, setState] = useState(initialState);
  const [backTarget, setBackTarget] = useState(null);
  const abortRef = useRef(null);
  const stateRef = useRef(initialState);
  const backStackRef = useRef([]);

  // Every state write goes through here so the stack can snapshot the current
  // view without re-rendering on a ref read.
  const commit = useCallback((next) => {
    stateRef.current = next;
    setState(next);
  }, []);

  const newController = useCallback(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    return controller;
  }, []);

  const describe = useCallback((snapshot) => {
    if (!snapshot) return null;
    return {
      question: snapshot.report?.question || "",
      live: isLiveStatus(snapshot.phase),
    };
  }, []);

  // Snapshots the view about to be replaced. An empty workspace isn't worth
  // going back to, so `idle` and report-less states are skipped.
  const pushCurrentView = useCallback(() => {
    const current = stateRef.current;
    if (current.phase === "idle" || !current.report) return;
    backStackRef.current = [...backStackRef.current, current];
    setBackTarget(describe(current));
  }, [describe]);

  // Follows an already-running job to completion. Shared by a fresh submit and
  // by goBack(), so a resumed run behaves exactly like one that was never
  // navigated away from.
  const watch = useCallback(
    async (job, controller, trackingKey) => {
      try {
        const final = await pollResearch(job.id, {
          signal: controller.signal,
          onUpdate: (update) => commit({ phase: update.status, report: update, error: null, trackingKey }),
        });
        commit({ phase: final.status, report: final, error: final.error || null, trackingKey });
      } catch (err) {
        if (err.name === "AbortError") return;
        commit({ phase: "error", report: null, error: err, trackingKey });
      }
    },
    [commit],
  );

  const runResearch = useCallback(
    async ({ question, sessionId, trackingKey = null }) => {
      // Asking a new question while one is still running is allowed (the wait
      // can be minutes). The in-flight run goes on the stack rather than being
      // thrown away - it keeps executing on the backend, so "back" can return
      // to it and pick the progress back up.
      pushCurrentView();
      const controller = newController();

      commit({ phase: "submitting", report: null, error: null, trackingKey });

      try {
        const initial = await submitResearch({ question, sessionId });
        if (controller.signal.aborted) return;

        if (TERMINAL_STATUSES.has(initial.status)) {
          commit({ phase: initial.status, report: initial, error: initial.error || null, trackingKey });
          return;
        }

        commit({ phase: initial.status || "planning", report: initial, error: null, trackingKey });
        await watch(initial, controller, trackingKey);
      } catch (err) {
        if (err.name === "AbortError") return;
        commit({ phase: "error", report: null, error: err, trackingKey });
      }
    },
    [commit, newController, pushCurrentView, watch],
  );

  // Re-displays a report already held in memory (e.g. from local research
  // history) with no network round-trip. If the selected run hasn't finished,
  // this reattaches to it instead of showing a frozen snapshot - Recent
  // Research lists questions from the moment they're sent, so an unfinished
  // one is a normal thing to click on.
  const loadCachedReport = useCallback(
    (report, trackingKey = null) => {
      pushCurrentView();
      const controller = newController();
      const phase = report.status || "completed";
      commit({ phase, report, error: report.error || null, trackingKey });

      if (isLiveStatus(phase) && report.id) {
        watch(report, controller, trackingKey);
      }
    },
    [commit, newController, pushCurrentView, watch],
  );

  const loadExample = useCallback(
    (exampleReport) => {
      pushCurrentView();
      abortRef.current?.abort();
      commit({ phase: "completed", report: exampleReport, error: null, trackingKey: null });
    },
    [commit, pushCurrentView],
  );

  const goBack = useCallback(() => {
    const stack = backStackRef.current;
    if (!stack.length) return;

    const previous = stack[stack.length - 1];
    backStackRef.current = stack.slice(0, -1);
    setBackTarget(describe(backStackRef.current[backStackRef.current.length - 1]));

    const controller = newController();
    commit(previous);

    if (isLiveStatus(previous.phase) && previous.report?.id) {
      watch(previous.report, controller, previous.trackingKey);
    }
  }, [commit, describe, newController, watch]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    backStackRef.current = [];
    setBackTarget(null);
    commit(initialState);
  }, [commit]);

  return { ...state, backTarget, runResearch, loadCachedReport, loadExample, goBack, reset };
}
