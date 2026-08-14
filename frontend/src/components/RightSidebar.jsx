import { ExampleReports } from "./ExampleReports";
import { ChatHistory } from "./ChatHistory";

export function RightSidebar({
  chats,
  activeChatId,
  onOpenExample,
  onNewChat,
  onSelectChat,
  onOpenTurn,
  onDeleteChat,
  mobileOpen,
  onClose,
}) {
  return (
    <aside className={`side-panel side-panel--right ${mobileOpen ? "side-panel--open" : ""}`} aria-label="Chats">
      <div className="side-panel__mobile-header mobile-only">
        <span>Chats</span>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close panel">
          ✕
        </button>
      </div>
      <ChatHistory
        chats={chats}
        activeId={activeChatId}
        onNewChat={onNewChat}
        onSelectChat={onSelectChat}
        onOpenTurn={onOpenTurn}
        onDeleteChat={onDeleteChat}
      />
      <ExampleReports onOpen={onOpenExample} />
    </aside>
  );
}
