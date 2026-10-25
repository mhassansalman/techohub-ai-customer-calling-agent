import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSession,
  endSession,
  getSessionStatus,
  safeErrorMessage,
  sendMessage,
} from "./api.js";

function toDisplayMessage(message) {
  return {
    id: message.message_id,
    sequence: message.sequence,
    role: message.role,
    text: message.text,
  };
}

export default function App() {
  const [session, setSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [starting, setStarting] = useState(true);
  const [sending, setSending] = useState(false);
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const sendingRef = useRef(false);
  const startingRef = useRef(false);
  const transcriptRef = useRef(null);
  const inputRef = useRef(null);

  const startConversation = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setStarting(true);
    setError("");
    setNotice("");

    try {
      const result = await createSession();
      const openedSession = result.session;
      setSession(openedSession);
      setMessages([
        {
          id: `disclosure-${openedSession.session_id}`,
          sequence: 0,
          role: "assistant",
          text: result.assistant_disclosure,
        },
      ]);

      try {
        const status = await getSessionStatus(openedSession.session_id);
        setSession(status);
        if (status.status !== "active") {
          setError("This conversation has already ended. Start a new conversation.");
        }
      } catch (statusError) {
        if (statusError.status === 404 || statusError.status === 409) {
          setSession((current) => ({ ...current, status: "closed" }));
          setError(safeErrorMessage(statusError, "check the conversation"));
        } else {
          setNotice("Conversation started. Its status could not be refreshed.");
        }
      }
    } catch (requestError) {
      setError(safeErrorMessage(requestError, "start a conversation"));
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
  }, []);

  useEffect(() => {
    void startConversation();
  }, [startConversation]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript) {
      transcript.scrollTop = transcript.scrollHeight;
    }
  }, [messages, sending]);

  const sessionActive = session?.status === "active";
  const busy = starting || sending || ending;

  async function handleSubmit(event) {
    event.preventDefault();
    const text = draft.trim();
    if (
      !text ||
      !sessionActive ||
      sendingRef.current ||
      busy
    ) {
      return;
    }

    sendingRef.current = true;
    setSending(true);
    setError("");
    setNotice("");
    try {
      const result = await sendMessage({
        sessionId: session.session_id,
        text,
      });
      const received = [
        toDisplayMessage(result.customer_message),
        toDisplayMessage(result.assistant_message),
      ];
      setMessages((current) =>
        [...current, ...received].sort((left, right) => left.sequence - right.sequence),
      );
      setDraft("");

      try {
        const status = await getSessionStatus(session.session_id);
        setSession(status);
        if (status.status !== "active") {
          setError("This conversation has ended. Start a new conversation to continue.");
        }
      } catch (statusError) {
        if (statusError.status === 404 || statusError.status === 409) {
          setSession((current) => ({ ...current, status: "closed" }));
          setError(safeErrorMessage(statusError, "refresh the conversation"));
        } else {
          setNotice("Your message was recorded, but conversation status could not be refreshed.");
        }
      }
    } catch (requestError) {
      if (requestError.status === 404 || requestError.status === 409) {
        setSession((current) => ({ ...current, status: "closed" }));
      }
      setError(safeErrorMessage(requestError, "send your message"));
    } finally {
      sendingRef.current = false;
      setSending(false);
      inputRef.current?.focus();
    }
  }

  async function handleEndConversation() {
    if (!sessionActive || busy) return;
    setEnding(true);
    setError("");
    setNotice("");
    try {
      const closedSession = await endSession(session.session_id);
      setSession(closedSession);
      setNotice("Conversation ended. Your messages were saved.");
    } catch (requestError) {
      if (requestError.status === 404 || requestError.status === 409) {
        setSession((current) => ({ ...current, status: "closed" }));
      }
      setError(safeErrorMessage(requestError, "end the conversation"));
    } finally {
      setEnding(false);
    }
  }

  const canCompose = sessionActive && !busy;

  return (
    <main className="page-shell">
      <header className="site-header">
        <a className="wordmark" href="/" aria-label="TECHOHUB home">
          <span className="wordmark-mark" aria-hidden="true">T</span>
          <span>TECHOHUB<span className="wordmark-period">.</span></span>
        </a>
        <span className="header-label">CUSTOMER CARE DEMO</span>
      </header>

      <section className="chat-panel" aria-labelledby="chat-title">
        <div className="chat-heading">
          <div className="assistant-avatar" aria-hidden="true">T</div>
          <div className="heading-copy">
            <p className="eyebrow">DEMO SALON</p>
            <h1 id="chat-title">How can we help?</h1>
            <p className="assistant-status">
              <span className={`status-dot ${sessionActive ? "is-online" : ""}`} />
              {starting ? "Connecting..." : sessionActive ? "Text assistant" : "Conversation closed"}
            </p>
          </div>
          {sessionActive && (
            <button
              className="end-button"
              type="button"
              onClick={handleEndConversation}
              disabled={busy}
            >
              End chat
            </button>
          )}
        </div>

        <div className="disclosure" role="note">
          <span className="disclosure-icon" aria-hidden="true">i</span>
          <p>
            You’re chatting with an <strong>automated assistant</strong>. Messages
            in this demo are stored to support the conversation.
          </p>
        </div>

        <p className="demo-note">
          Demo mode: messages are recorded, but automated answers and salon
          actions are not connected yet.
        </p>

        <div
          className="transcript"
          role="log"
          aria-label="Conversation"
          aria-live="polite"
          aria-relevant="additions text"
          ref={transcriptRef}
        >
          {messages.map((message) => (
            <article
              className={`message-row ${message.role === "customer" ? "from-customer" : "from-assistant"}`}
              key={message.id}
              data-role={message.role}
            >
              {message.role === "assistant" && (
                <span className="message-avatar" aria-hidden="true">T</span>
              )}
              <div className="message-content">
                <span className="message-sender">
                  {message.role === "customer" ? "You" : "TECHOHUB assistant"}
                </span>
                <p className="message-bubble">{message.text}</p>
              </div>
            </article>
          ))}
          {sending && (
            <div className="sending-state" role="status" aria-live="polite">
              <span className="typing-dots" aria-hidden="true"><i /><i /><i /></span>
              <span>Sending your message…</span>
            </div>
          )}
        </div>

        {error && (
          <div className="feedback feedback-error" role="alert">
            <span>{error}</span>
            {!session && !starting && (
              <button type="button" onClick={() => void startConversation()}>
                Try again
              </button>
            )}
            {session && !sessionActive && !starting && (
              <button type="button" onClick={() => void startConversation()}>
                Start a new conversation
              </button>
            )}
          </div>
        )}
        {notice && (
          <div className="feedback feedback-notice" role="status">
            <span>{notice}</span>
            {session && !sessionActive && !starting && (
              <button type="button" onClick={() => void startConversation()}>
                Start a new conversation
              </button>
            )}
          </div>
        )}

        <form className="composer" onSubmit={handleSubmit}>
          <label className="visually-hidden" htmlFor="message-input">
            Your message
          </label>
          <textarea
            id="message-input"
            ref={inputRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={sessionActive ? "Write a message…" : "Chat is unavailable"}
            rows={1}
            maxLength={2000}
            disabled={!canCompose}
            aria-describedby="composer-help"
          />
          <button
            className="send-button"
            type="submit"
            aria-label="Send message"
            disabled={!canCompose || !draft.trim()}
          >
            <span aria-hidden="true">↑</span>
          </button>
        </form>
        <div className="composer-footer" id="composer-help">
          <span>Press <kbd>Enter</kbd> to send · <kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line</span>
          <span>{draft.length}/2000</span>
        </div>
      </section>

      <footer className="page-footer">
        <span>TECHOHUB · Academic prototype</span>
        {session?.session_id && (
          <span className="session-reference" title={session.session_id}>
            Session {session.session_id.slice(0, 8)}
          </span>
        )}
      </footer>
    </main>
  );
}
