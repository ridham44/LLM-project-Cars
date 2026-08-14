import { WelcomeState } from "./WelcomeState";
import { SuggestedQuestions } from "./SuggestedQuestions";
import { ResearchProgress } from "./ResearchProgress";
import { ResearchReportView } from "./ResearchReportView";
import { isLiveStatus } from "../constants";

export function CenterWorkspace({ phase, report, error, onSelectQuestion, onCancel, backTarget, onBack }) {
  const isIdle = phase === "idle";
  const isBusy = isLiveStatus(phase);
  const isError = phase === "error";
  const isCompleted = phase === "completed" && report;
  // A real, evidence-grounded answer can exist before the job is fully
  // "completed" (see orchestrator.py's on_progress hook) - show it as soon
  // as it's there instead of a blank spinner for the whole verification
  // pass, with ResearchReportView's isVerifying flag making clear it's
  // still being checked.
  const hasPartialAnswer = isBusy && Boolean(report?.summary);

  return (
    <main className="center-workspace">
      {/* Opening a recent run or an example replaces the workspace - this is
          the way back to whatever it replaced, including a run that is still
          in progress (useResearch resumes its polling). */}
      {backTarget && (
        <button type="button" className="view-back" onClick={onBack}>
          <span className="view-back__arrow" aria-hidden="true">
            ←
          </span>
          <span className="view-back__label">
            Back to {backTarget.live ? "the run in progress" : "your last result"}
          </span>
          {backTarget.question && <span className="view-back__question muted">{backTarget.question}</span>}
        </button>
      )}

      {isIdle && (
        <>
          <WelcomeState />
          <SuggestedQuestions onSelect={onSelectQuestion} />
        </>
      )}
      {isBusy && !hasPartialAnswer && <ResearchProgress phase={phase} report={report} error={error} onCancel={onCancel} />}
      {isError && <ResearchProgress phase={phase} report={report} error={error} onCancel={null} />}
      {(isCompleted || hasPartialAnswer) && <ResearchReportView report={report} isVerifying={!isCompleted} onCancel={hasPartialAnswer ? onCancel : null} />}
    </main>
  );
}
