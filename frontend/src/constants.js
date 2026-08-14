// No manual mode/model selector - the backend classifies intent and
// complexity itself (see orchestrator.py) and picks whichever models the
// question actually needs. What ran is surfaced read-only via
// report.routing, rendered by RoutingInfo.jsx.
export const PIPELINE_STEPS = [
  "Query Understanding",
  "Research Planning",
  "Document Retrieval",
  "Evidence Ranking",
  "Researcher Model",
  "Analyst Model",
  "Claim Verification",
  "Judge Synthesis",
];

// Statuses that mean a backend job is still working - the frontend mirrors
// whatever the job reports (backend/api.py, orchestrator.py's on_progress
// hook). Shared rather than redeclared per component so "is this run still
// going" can't answer differently in the workspace, the composer and the
// Recent Research list.
export const LIVE_STATUSES = new Set([
  "submitting",
  "processing",
  "planning",
  "retrieving",
  "analyzing",
  "verifying",
  "synthesizing",
]);

export function isLiveStatus(status) {
  return LIVE_STATUSES.has(status);
}

export const INTENT_LABEL = {
  FACTUAL: "Factual",
  RESEARCH: "Research",
  COMPARE: "Compare",
  VERIFY: "Verify",
  SUMMARY: "Summary",
  FOLLOWUP: "Follow-up",
};

export function humanizeIntent(intents) {
  if (!intents || intents.length === 0) return "—";
  return intents.map((i) => INTENT_LABEL[i] || i).join(" + ");
}

// CLAIM_STATUS_META (Supported / Contradicted / ...) was removed along with the
// verification models that produced those statuses. ClaimsPanel now shows
// whether a claim is tied to evidence, which is something the system actually
// knows - see the comment at the top of ClaimsPanel.jsx.

export const SOURCE_TYPE_LABEL = {
  official: "Official Source",
  government: "Government Filing",
  research: "Research Paper",
  industry: "Industry Publication",
  media: "Media",
  other: "Other Source",
};

export const SUGGESTED_QUESTIONS = [
  {
    question: "What is the W16 engine's displacement and power output?",
    description: "A quick factual lookup - answered by a single fast model.",
  },
  {
    question: "Research the engineering behind the Bugatti Chiron.",
    description: "Open-ended research over the Chiron's technical documents.",
  },
  {
    // The knowledge base holds Bugatti press material, Ferrari financial
    // filings and Pagani notes - so a cross-marque comparison is one of the
    // three, not an arbitrary hypercar pairing. Retrieval scopes itself to
    // whichever marques a question names (see backend/retrieval.py).
    question: "Compare Bugatti and Pagani on engineering philosophy.",
    description: "Cross-marque comparison - searches both marques' documents.",
  },
  {
    question: "Summarize Ferrari's Q2 2026 results.",
    description: "Scoped to the Ferrari filings, with claims checked against them.",
  },
];

export const DEFAULT_RELATED_QUESTIONS = [
  "Compare their engines",
  "Which uses more advanced aerodynamics?",
  "are you sure? double-check that",
  "Show supporting sources",
];

export function humanizeModelVar(varName) {
  return varName
    .replace(/_MODEL$/, "")
    .toLowerCase()
    .replace(/(^|_)(\w)/g, (_, sep, letter) => (sep ? " " : "") + letter.toUpperCase());
}
