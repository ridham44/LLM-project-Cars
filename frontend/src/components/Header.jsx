function StatusDot({ label, online }) {
  return (
    <span className="header-status">
      <span className={`status-dot ${online ? "status-dot--success" : "status-dot--neutral"}`} aria-hidden="true" />
      {label}
    </span>
  );
}

export function Header({ systemStatus, chatTitle, onNewChat, onToggleLeftDrawer, onToggleRightDrawer }) {
  const modelCount = Object.keys(systemStatus.models).length;
  const modelsReady = Object.values(systemStatus.models).filter((m) => m.available).length;

  return (
    <header className="app-header">
      <div className="app-header__left">
        <button
          type="button"
          className="icon-button mobile-only"
          aria-label="Toggle research info panel"
          onClick={onToggleLeftDrawer}
        >
          ☰ Info
        </button>
        <div className="app-header__brand">
          <span className="app-header__title">LOCAL AI RESEARCH ENGINE</span>
          {/* Which conversation you're asking into decides what a follow-up
              like "are you sure?" resolves against, so it belongs on screen. */}
          <span className="app-header__subtitle">{chatTitle || "Private · Local · Evidence Based"}</span>
        </div>
      </div>

      <div className="app-header__status desktop-only" role="status">
        <StatusDot label="Ollama" online={systemStatus.ollamaReachable} />
        <StatusDot label="Backend" online={systemStatus.backendReachable} />
        <StatusDot label="Knowledge Base" online={systemStatus.knowledgeBase.ready} />
        {modelCount > 0 && <span className="header-status muted">{modelsReady}/{modelCount} models</span>}
      </div>

      <div className="app-header__actions">
        <button type="button" className="header-new-chat" onClick={onNewChat}>
          + New chat
        </button>
        <button
          type="button"
          className="icon-button mobile-only"
          aria-label="Toggle chats panel"
          onClick={onToggleRightDrawer}
        >
          ☰ Chats
        </button>
        <button type="button" className="icon-button" aria-label="Settings" disabled title="Settings (not yet implemented)">
          ⚙
        </button>
      </div>
    </header>
  );
}
