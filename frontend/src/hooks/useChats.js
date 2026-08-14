import { useCallback, useEffect, useMemo, useState } from "react";
import { chatTitle, loadChats, newId, saveChats } from "../utils/chats";

// Owns the conversation list: which chat is active, what turns each one holds,
// and the running state of each turn.
//
// A chat's id doubles as the backend session id. That is the whole point of
// the split - asking inside a chat continues that conversation's context on
// the backend, and "New chat" starts a fresh one, instead of every question
// silently sharing one per-tab session the user could neither see nor reset.
export function useChats() {
  const [chats, setChats] = useState(() => loadChats());
  const [activeId, setActiveId] = useState(() => loadChats()[0]?.id || null);

  useEffect(() => {
    saveChats(chats);
  }, [chats]);

  const activeChat = useMemo(() => chats.find((chat) => chat.id === activeId) || null, [chats, activeId]);

  // Reuses the active chat when it's still empty, so clicking "New chat"
  // repeatedly doesn't litter the list with blank conversations.
  const newChat = useCallback(() => {
    let created = null;
    setChats((prev) => {
      const active = prev.find((chat) => chat.id === activeId);
      if (active && active.turns.length === 0) {
        created = active.id;
        return prev;
      }
      const chat = { id: newId(), title: "New chat", createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), turns: [] };
      created = chat.id;
      return [chat, ...prev];
    });
    if (created) setActiveId(created);
    return created;
  }, [activeId]);

  const selectChat = useCallback((chatId) => {
    setActiveId(chatId);
  }, []);

  const deleteChat = useCallback((chatId) => {
    setChats((prev) => {
      const remaining = prev.filter((chat) => chat.id !== chatId);
      setActiveId((current) => (current === chatId ? remaining[0]?.id || null : current));
      return remaining;
    });
  }, []);

  // Records a question the moment it's sent and returns both the turn key
  // (for progress updates) and the chat id (which is the session id the
  // request must be sent with, so the turn and the backend context can't
  // disagree about which conversation this is).
  const recordPending = useCallback(
    (question) => {
      const turn = {
        key: newId(),
        id: null,
        question,
        intent: [],
        timestamp: new Date().toISOString(),
        status: "running",
        report: null,
      };

      let chatId = activeId;
      setChats((prev) => {
        const existing = prev.find((chat) => chat.id === activeId);
        if (!existing) {
          const chat = {
            id: chatId || newId(),
            title: chatTitle(question),
            createdAt: turn.timestamp,
            updatedAt: turn.timestamp,
            turns: [turn],
          };
          chatId = chat.id;
          return [chat, ...prev];
        }
        return moveToFront(
          prev.map((chat) =>
            chat.id !== activeId
              ? chat
              : {
                  ...chat,
                  title: chat.turns.length === 0 ? chatTitle(question) : chat.title,
                  updatedAt: turn.timestamp,
                  turns: [...chat.turns, turn],
                },
          ),
          activeId,
        );
      });

      if (!activeId) setActiveId(chatId);
      return { key: turn.key, chatId };
    },
    [activeId],
  );

  const updateTurn = useCallback((turnKey, { report, status }) => {
    if (!turnKey) return;
    setChats((prev) =>
      prev.map((chat) => {
        if (!chat.turns.some((turn) => turn.key === turnKey)) return chat;
        return {
          ...chat,
          updatedAt: new Date().toISOString(),
          turns: chat.turns.map((turn) => {
            if (turn.key !== turnKey) return turn;
            const finished = status === "completed" || status === "error";
            return {
              ...turn,
              id: report?.id || turn.id,
              status: status || turn.status,
              intent: report?.routing?.intent?.length ? report.routing.intent : turn.intent,
              timestamp: finished ? report?.completedAt || new Date().toISOString() : turn.timestamp,
              // The job payload carries no question until the orchestrator's
              // first progress hook fires (backend/api.py's get_research), so
              // keep the one we asked with.
              report: report ? { ...report, question: report.question || turn.question } : turn.report,
            };
          }),
        };
      }),
    );
  }, []);

  return { chats, activeChat, activeId, newChat, selectChat, deleteChat, recordPending, updateTurn };
}

function moveToFront(chats, chatId) {
  const index = chats.findIndex((chat) => chat.id === chatId);
  if (index <= 0) return chats;
  return [chats[index], ...chats.slice(0, index), ...chats.slice(index + 1)];
}
