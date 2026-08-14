import { useEffect, useRef, useState } from "react";
import { Header } from "./Header";
import { LeftSidebar } from "./LeftSidebar";
import { RightSidebar } from "./RightSidebar";
import { CenterWorkspace } from "./CenterWorkspace";
import { RelatedQuestions } from "./RelatedQuestions";
import { ResearchComposer } from "./ResearchComposer";
import { useResearch } from "../hooks/useResearch";
import { useChats } from "../hooks/useChats";
import { useSystemStatus } from "../hooks/useSystemStatus";
import { isLiveStatus } from "../constants";

export function ResearchWorkspace() {
  const [question, setQuestion] = useState("");
  const [lastSubmitted, setLastSubmitted] = useState("");
  const [leftDrawerOpen, setLeftDrawerOpen] = useState(false);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  // The turn key of the send in flight, so an error can only restore the text
  // for THAT send - see the restore effect below.
  const pendingKeyRef = useRef(null);

  const { phase, report, error, backTarget, trackingKey, runResearch, loadCachedReport, loadExample, goBack, reset } =
    useResearch();
  const { chats, activeChat, activeId, newChat, selectChat, deleteChat, recordPending, updateTurn } = useChats();
  const systemStatus = useSystemStatus();

  // Keeps the turn row for whichever run is on screen in step with it - from
  // "running" through to the finished report, which is what makes the row
  // openable afterwards. trackingKey travels with the view, so this never
  // writes a cached/example report onto a live run's row.
  useEffect(() => {
    if (!trackingKey || report?.isExample) return;
    updateTurn(trackingKey, { report, status: phase });
  }, [trackingKey, phase, report, updateTurn]);

  // The composer clears as soon as a question is sent (so a follow-up can be
  // typed immediately) and the text comes back ONLY if that very send failed,
  // so nothing typed is lost.
  //
  // The trackingKey guard is the point: without it, opening a past chat whose
  // run had errored would put a stale question into the input, because the
  // restored view's phase is "error" too. Restoring is about the send that just
  // failed, not about any errored report that happens to be on screen.
  useEffect(() => {
    if (phase !== "error" || !lastSubmitted) return;
    if (trackingKey && trackingKey !== pendingKeyRef.current) return;
    setQuestion(lastSubmitted);
    pendingKeyRef.current = null;
  }, [phase, trackingKey, lastSubmitted]);

  const busy = isLiveStatus(phase);

  function startResearch(text) {
    setLastSubmitted(text);
    setQuestion("");
    // The turn is listed before the backend has even handed back a job id, and
    // the chat it lands in supplies the session id - so a follow-up resolves
    // against the right conversation (backend/context_store.py) instead of
    // against whatever question happened to be asked last in the tab.
    const { key, chatId } = recordPending(text);
    pendingKeyRef.current = key;
    runResearch({ question: text, sessionId: chatId, trackingKey: key });
  }

  function handleNewChat() {
    setRightDrawerOpen(false);
    setQuestion("");
    newChat();
    reset();
  }

  // Switching chats shows that conversation's most recent answer, so the
  // workspace matches the chat you're now asking into.
  function handleSelectChat(chat) {
    setRightDrawerOpen(false);
    selectChat(chat.id);
    const latest = [...chat.turns].reverse().find((turn) => turn.report);
    if (latest) loadCachedReport(latest.report, latest.key);
    else reset();
  }

  // Opening a past turn shows its report. It does NOT put the old question back
  // in the composer: the input belongs to the user, and pre-filling it meant
  // that reading an earlier answer left text you then had to clear before you
  // could type. Nothing writes to the composer except typing and a submit
  // clearing it.
  function handleOpenTurn(turn) {
    setLeftDrawerOpen(false);
    setRightDrawerOpen(false);
    if (turn.report) loadCachedReport(turn.report, turn.key);
  }

  function handleOpenExample(exampleReport) {
    setRightDrawerOpen(false);
    loadExample(exampleReport);
  }

  return (
    <div className="app-shell">
      <Header
        systemStatus={systemStatus}
        chatTitle={activeChat?.title}
        onNewChat={handleNewChat}
        onToggleLeftDrawer={() => setLeftDrawerOpen((v) => !v)}
        onToggleRightDrawer={() => setRightDrawerOpen((v) => !v)}
      />

      <div className="app-body">
        <LeftSidebar systemStatus={systemStatus} mobileOpen={leftDrawerOpen} onClose={() => setLeftDrawerOpen(false)} />

        <CenterWorkspace
          phase={phase}
          report={report}
          error={error}
          onSelectQuestion={startResearch}
          onCancel={reset}
          backTarget={backTarget}
          onBack={goBack}
        />

        <RightSidebar
          chats={chats}
          activeChatId={activeId}
          onOpenExample={handleOpenExample}
          onNewChat={handleNewChat}
          onSelectChat={handleSelectChat}
          onOpenTurn={handleOpenTurn}
          onDeleteChat={deleteChat}
          mobileOpen={rightDrawerOpen}
          onClose={() => setRightDrawerOpen(false)}
        />
      </div>

      {phase === "completed" && report && <RelatedQuestions onSelect={startResearch} />}

      <ResearchComposer
        question={question}
        onQuestionChange={setQuestion}
        onSubmit={startResearch}
        busy={busy}
        onCancel={reset}
        followUp={Boolean(activeChat?.turns.length)}
      />

      {(leftDrawerOpen || rightDrawerOpen) && (
        <button
          type="button"
          className="drawer-backdrop"
          aria-label="Close panel"
          onClick={() => {
            setLeftDrawerOpen(false);
            setRightDrawerOpen(false);
          }}
        />
      )}
    </div>
  );
}
