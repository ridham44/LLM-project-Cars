import { formatRelativeDate } from "../utils/format";
import { humanizeIntent, isLiveStatus } from "../constants";

function TurnRow({ turn, onOpen }) {
  const running = turn.status === "running" || isLiveStatus(turn.status);
  const failed = turn.status === "error";

  return (
    <li>
      <button
        type="button"
        className="chat-turn"
        onClick={() => onOpen(turn)}
        disabled={!turn.report}
        title={running ? "Still running - open to follow its progress" : turn.question}
      >
        <span className="chat-turn__question">{turn.question}</span>
        <span className="muted chat-turn__meta">
          {running ? (
            <>
              <span className="chat-turn__pulse" aria-hidden="true" />
              Running{turn.report ? " - open to follow" : ""}
            </>
          ) : (
            <>{failed ? "Failed" : humanizeIntent(turn.intent)}</>
          )}
        </span>
      </button>
    </li>
  );
}

// The conversation list. Chats are ordered most-recent-first; the active one
// expands to show its turns so a follow-up's context is visible, which is the
// thing a flat list of one-off runs could never show.
export function ChatHistory({ chats, activeId, onNewChat, onSelectChat, onOpenTurn, onDeleteChat }) {
  return (
    <section className="sidebar-card" aria-label="Chats">
      <div className="chat-history__header">
        <h2>Chats</h2>
        <button type="button" className="chat-history__new" onClick={onNewChat}>
          + New chat
        </button>
      </div>

      {chats.length === 0 ? (
        <p className="muted">No chats yet. Ask a question to start one.</p>
      ) : (
        <ul className="sidebar-card__list">
          {chats.map((chat) => {
            const active = chat.id === activeId;
            const running = chat.turns.some((turn) => turn.status === "running" || isLiveStatus(turn.status));

            return (
              <li key={chat.id} className={`chat-entry ${active ? "chat-entry--active" : ""}`}>
                <div className="chat-entry__row">
                  <button type="button" className="chat-entry__button" onClick={() => onSelectChat(chat)} title={chat.title}>
                    <span className="chat-entry__title">{chat.title}</span>
                    <span className="muted chat-entry__meta">
                      {running && <span className="chat-turn__pulse" aria-hidden="true" />}
                      {formatRelativeDate(chat.updatedAt)} &middot; {chat.turns.length}{" "}
                      {chat.turns.length === 1 ? "question" : "questions"}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="chat-entry__delete"
                    onClick={() => onDeleteChat(chat.id)}
                    aria-label={`Delete chat: ${chat.title}`}
                    title="Delete chat"
                  >
                    ✕
                  </button>
                </div>

                {active && chat.turns.length > 0 && (
                  <ul className="chat-entry__turns">
                    {chat.turns.map((turn) => (
                      <TurnRow key={turn.key} turn={turn} onOpen={onOpenTurn} />
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
