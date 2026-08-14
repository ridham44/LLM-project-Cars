// Chat persistence. A "chat" is one conversation: its id IS the session id
// sent to the backend, so continuing a chat continues the backend's follow-up
// context (backend/context_store.py resolves "are you sure?" / "what about its
// weight?" against the last turn of that session), and starting a new chat
// starts that context clean.
//
// Stored in localStorage rather than sessionStorage so history survives a
// reload, the way it does in ChatGPT/Gemini. Reports are self-contained JSON
// and are cached here in full, because the backend has no history store - job
// state expires after 30 minutes (backend/jobs.py) and is never written to
// disk, so this is the only place a past answer can be read back from.

const STORAGE_KEY = "research-chats-v1";

// Reports carry evidence excerpts and can run to tens of KB. These caps keep
// the store inside a typical 5MB localStorage budget; saveChats() trims
// further if a write is rejected anyway.
const MAX_CHATS = 12;
const MAX_TURNS_PER_CHAT = 25;
const MAX_TITLE_CHARS = 64;

export function newId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function chatTitle(question) {
  const trimmed = (question || "").trim();
  if (!trimmed) return "New chat";
  return trimmed.length > MAX_TITLE_CHARS ? `${trimmed.slice(0, MAX_TITLE_CHARS - 1)}…` : trimmed;
}

export function loadChats() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed?.chats) ? parsed.chats : [];
  } catch {
    // Corrupt or unreadable storage is not worth failing the app over - an
    // empty history is a fine starting point.
    return [];
  }
}

export function saveChats(chats) {
  if (typeof window === "undefined") return;

  const trimmed = chats.slice(0, MAX_CHATS).map((chat) => ({
    ...chat,
    turns: chat.turns.slice(-MAX_TURNS_PER_CHAT),
  }));

  // Cached reports make the payload unpredictable, so a quota rejection is a
  // normal outcome, not an exceptional one: drop the oldest chats until it
  // fits rather than losing the write (and the current conversation with it).
  for (let keep = trimmed.length; keep > 0; keep -= 1) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ chats: trimmed.slice(0, keep) }));
      return;
    } catch {
      /* try again with fewer chats */
    }
  }

  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing more to do - history is best-effort */
  }
}
