import { DocumentUploader } from "./DocumentUploader";

export function ResearchComposer({ question, onQuestionChange, onSubmit, busy, onCancel, followUp }) {
  // The composer stays usable while a run is in flight. A research-tier
  // question legitimately takes minutes on this hardware (see README.md's
  // "Hardware reality"), and a disabled textarea meant the whole wait was
  // dead time - you couldn't even draft the next question. Sending during a
  // run doesn't discard it either: useResearch stacks the running job so the
  // back control returns to it, and the backend worker keeps going regardless
  // (backend/jobs.py).
  function handleSubmit() {
    const trimmed = question.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      handleSubmit();
    }
  }

  return (
    <footer className="composer">
      <div className="composer__box">
        <label htmlFor="research-question" className="visually-hidden">
          Research question
        </label>
        <textarea
          id="research-question"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            busy
              ? "Still working - you can type the next question now..."
              : followUp
                ? "Ask a follow-up - \"are you sure?\", \"what about its weight?\"..."
                : "Ask anything about your knowledge base..."
          }
          rows={2}
        />

        <div className="composer__toolbar">
          <DocumentUploader variant="compact" />

          <span className="composer__hint muted">
            {busy
              ? "Running. Sending now moves on - the current run keeps going and stays reachable via Back."
              : "The system figures out how to answer - no mode to pick."}
          </span>

          {busy && (
            <button type="button" className="composer__send composer__send--stop" onClick={onCancel} aria-label="Stop research">
              Stop
            </button>
          )}
          <button
            type="button"
            className="composer__send"
            onClick={handleSubmit}
            disabled={!question.trim()}
            aria-label={busy ? "Send next question" : "Send research question"}
          >
            ↑
          </button>
        </div>
      </div>
    </footer>
  );
}
