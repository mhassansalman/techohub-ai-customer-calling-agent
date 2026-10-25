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

function getMicrophoneErrorMessage(error) {
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return "Microphone permission was denied. Allow microphone access or type your message.";
  }
  if (error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError") {
    return "No microphone was found. Connect a microphone or type your message.";
  }
  if (error?.name === "NotReadableError" || error?.name === "TrackStartError") {
    return "The microphone could not be opened. Check that another app is not using it, or type your message.";
  }
  return "Microphone access failed. Check your microphone or type your message.";
}

function getRecognitionErrorMessage(error) {
  const messages = {
    "audio-capture": "No microphone audio was detected. Check your microphone or type your message.",
    "not-allowed": "Microphone permission was denied. Allow microphone access or type your message.",
    "service-not-allowed": "Speech recognition is blocked by the browser. You can type your message instead.",
    "no-speech": "No speech was recognized. Please try again or type your message.",
    network: "Speech recognition could not reach its service. Check your connection or type your message.",
    aborted: "Voice input was cancelled.",
  };
  return messages[error] ?? "Speech recognition failed. Please try again or type your message.";
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
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceFeedback, setVoiceFeedback] = useState("");
  const [voiceFeedbackIsError, setVoiceFeedbackIsError] = useState(false);
  const sendingRef = useRef(false);
  const startingRef = useRef(false);
  const recognitionRef = useRef(null);
  const voiceAttemptRef = useRef(0);
  const voiceSubmissionRef = useRef(false);
  const sessionRef = useRef(null);
  const observedSessionIdRef = useRef(null);
  const mountedRef = useRef(true);
  const transcriptRef = useRef(null);
  const inputRef = useRef(null);

  function updateVoiceFeedback(message, { isError = false } = {}) {
    setVoiceFeedback(message);
    setVoiceFeedbackIsError(isError);
  }

  function cancelRecognition(message = "Voice input cancelled.") {
    voiceAttemptRef.current += 1;
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      recognition.abort();
    }
    voiceSubmissionRef.current = false;
    setListening(false);
    updateVoiceFeedback(message);
  }

  function stopSpeech(message = "Speech playback stopped.") {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setSpeaking(false);
    updateVoiceFeedback(message);
  }

  const startConversation = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setStarting(true);
    setError("");
    setNotice("");

    try {
      const result = await createSession();
      const openedSession = result.session;
      sessionRef.current = openedSession;
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
        sessionRef.current = status;
        setSession(status);
        if (status.status !== "active") {
          setError("This conversation has already ended. Start a new conversation.");
        }
      } catch (statusError) {
        if (statusError.status === 404 || statusError.status === 409) {
          const closedSession = { ...openedSession, status: "closed" };
          sessionRef.current = closedSession;
          setSession(closedSession);
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
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      voiceAttemptRef.current += 1;
      const recognition = recognitionRef.current;
      recognitionRef.current = null;
      if (recognition) {
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        recognition.abort();
      }
      window.speechSynthesis?.cancel();
    };
  }, []);

  useEffect(() => {
    const currentSessionId = session?.session_id ?? null;
    const previousSessionId = observedSessionIdRef.current;
    if (previousSessionId && currentSessionId !== previousSessionId) {
      cancelRecognition("Voice input stopped because the conversation changed.");
      stopSpeech("Speech playback stopped because the conversation changed.");
    }
    observedSessionIdRef.current = currentSessionId;
    sessionRef.current = session;
  }, [session]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript) {
      transcript.scrollTop = transcript.scrollHeight;
    }
  }, [messages, sending]);

  const sessionActive = session?.status === "active";
  const busy = starting || sending || ending;

  async function submitMessage(text, { speakResponse = false, sessionId } = {}) {
    const messageText = text.trim();
    const targetSessionId = sessionId ?? sessionRef.current?.session_id;
    if (
      !messageText ||
      !targetSessionId ||
      sessionRef.current?.status !== "active" ||
      sendingRef.current ||
      busy
    ) {
      return false;
    }

    sendingRef.current = true;
    setSending(true);
    setError("");
    setNotice("");
    try {
      const result = await sendMessage({
        sessionId: targetSessionId,
        text: messageText,
      });
      if (
        !mountedRef.current ||
        sessionRef.current?.session_id !== targetSessionId
      ) {
        return false;
      }
      const received = [
        toDisplayMessage(result.customer_message),
        toDisplayMessage(result.assistant_message),
      ];
      setMessages((current) =>
        [...current, ...received].sort((left, right) => left.sequence - right.sequence),
      );
      setDraft("");
      if (speakResponse) {
        speakAssistantResponse(result.assistant_message.text, targetSessionId);
      }

      try {
        const status = await getSessionStatus(targetSessionId);
        if (
          !mountedRef.current ||
          sessionRef.current?.session_id !== targetSessionId
        ) {
          return true;
        }
        sessionRef.current = status;
        setSession(status);
        if (status.status !== "active") {
          setError("This conversation has ended. Start a new conversation to continue.");
        }
      } catch (statusError) {
        if (!mountedRef.current) return true;
        if (statusError.status === 404 || statusError.status === 409) {
          const closedSession = { ...sessionRef.current, status: "closed" };
          sessionRef.current = closedSession;
          setSession(closedSession);
          setError(safeErrorMessage(statusError, "refresh the conversation"));
        } else {
          setNotice("Your message was recorded, but conversation status could not be refreshed.");
        }
      }
      return true;
    } catch (requestError) {
      if (!mountedRef.current) return false;
      if (requestError.status === 404 || requestError.status === 409) {
        const closedSession = { ...sessionRef.current, status: "closed" };
        sessionRef.current = closedSession;
        setSession(closedSession);
      }
      setError(safeErrorMessage(requestError, "send your message"));
      return false;
    } finally {
      sendingRef.current = false;
      if (mountedRef.current) {
        setSending(false);
        inputRef.current?.focus();
      }
    }
  }

  function speakAssistantResponse(text, sessionId) {
    if (!text?.trim()) {
      updateVoiceFeedback("The assistant returned no text to speak.");
      return;
    }
    if (!window.speechSynthesis || typeof window.SpeechSynthesisUtterance !== "function") {
      updateVoiceFeedback(
        "Voice reply is unavailable in this browser. The assistant response is shown above.",
      );
      return;
    }

    window.speechSynthesis.cancel();
    setSpeaking(false);
    updateVoiceFeedback("Speaking the assistant response.");
    const utterance = new window.SpeechSynthesisUtterance(text);
    utterance.onstart = () => {
      if (
        mountedRef.current &&
        sessionRef.current?.session_id === sessionId
      ) {
        setSpeaking(true);
      }
    };
    utterance.onend = () => {
      if (
        mountedRef.current &&
        sessionRef.current?.session_id === sessionId
      ) {
        setSpeaking(false);
        updateVoiceFeedback("Voice reply finished.");
      }
    };
    utterance.onerror = (event) => {
      if (
        !mountedRef.current ||
        sessionRef.current?.session_id !== sessionId
      ) {
        return;
      }
      setSpeaking(false);
      if (event.error === "canceled" || event.error === "interrupted") {
        updateVoiceFeedback("Speech playback stopped.");
      } else {
        updateVoiceFeedback(
          "The assistant response is shown above, but speech playback failed.",
        );
      }
    };
    window.speechSynthesis.speak(utterance);
  }

  function handleStartVoice() {
    if (!sessionActive || busy || listening) return;

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      updateVoiceFeedback(
        "Voice input is not supported in this browser. You can type your message instead.",
        { isError: true },
      );
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      updateVoiceFeedback(
        "Microphone access is unavailable here. You can type your message instead.",
        { isError: true },
      );
      return;
    }

    const sessionId = session.session_id;
    const attemptId = ++voiceAttemptRef.current;
    voiceSubmissionRef.current = false;
    setListening(true);
    setError("");
    updateVoiceFeedback("Requesting microphone access…");

    void (async () => {
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (permissionError) {
        if (attemptId !== voiceAttemptRef.current || !mountedRef.current) return;
        setListening(false);
        updateVoiceFeedback(getMicrophoneErrorMessage(permissionError), { isError: true });
        return;
      } finally {
        stream?.getTracks().forEach((track) => track.stop());
      }

      if (
        attemptId !== voiceAttemptRef.current ||
        !mountedRef.current ||
        sessionRef.current?.session_id !== sessionId ||
        sessionRef.current?.status !== "active"
      ) {
        return;
      }

      const recognition = new SpeechRecognition();
      let recognitionFailed = false;
      recognition.lang = "en-US";
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      recognitionRef.current = recognition;
      updateVoiceFeedback("Listening… Speak now, or cancel voice input.");

      recognition.onresult = (event) => {
        if (attemptId !== voiceAttemptRef.current || voiceSubmissionRef.current) return;
        const transcript = Array.from(event.results)
          .filter((result) => result.isFinal)
          .map((result) => result[0]?.transcript ?? "")
          .join(" ")
          .trim();
        if (!transcript) return;

        voiceSubmissionRef.current = true;
        setDraft(transcript);
        updateVoiceFeedback("Speech recognized. Sending your message…");
        recognition.stop();
        void submitMessage(transcript, { speakResponse: true, sessionId });
      };
      recognition.onerror = (event) => {
        recognitionFailed = true;
        if (attemptId !== voiceAttemptRef.current || !mountedRef.current) return;
        setListening(false);
        recognitionRef.current = null;
        voiceSubmissionRef.current = false;
        updateVoiceFeedback(getRecognitionErrorMessage(event.error), { isError: true });
      };
      recognition.onend = () => {
        if (recognitionRef.current === recognition) {
          recognitionRef.current = null;
        }
        if (attemptId !== voiceAttemptRef.current || !mountedRef.current) return;
        setListening(false);
        if (!voiceSubmissionRef.current && !recognitionFailed) {
          updateVoiceFeedback("No speech was recognized. Please try again or type your message.");
        }
      };

      try {
        recognition.start();
      } catch (recognitionError) {
        recognitionRef.current = null;
        setListening(false);
        updateVoiceFeedback(getRecognitionErrorMessage(recognitionError.name), { isError: true });
      }
    })();
  }

  function handleCancelVoice() {
    cancelRecognition();
  }

  function handleSubmit(event) {
    event.preventDefault();
    void submitMessage(draft);
  }

  async function handleEndConversation() {
    if (!sessionActive || busy) return;
    if (listening) cancelRecognition("Voice input stopped because the conversation is ending.");
    stopSpeech();
    setEnding(true);
    setError("");
    setNotice("");
    try {
      const closedSession = await endSession(session.session_id);
      sessionRef.current = closedSession;
      setSession(closedSession);
      setNotice("Conversation ended. Your messages were saved.");
    } catch (requestError) {
      if (requestError.status === 404 || requestError.status === 409) {
        const closedSession = { ...sessionRef.current, status: "closed" };
        sessionRef.current = closedSession;
        setSession(closedSession);
      }
      setError(safeErrorMessage(requestError, "end the conversation"));
    } finally {
      setEnding(false);
    }
  }

  const canCompose = sessionActive && !busy && !listening;

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
          Demo mode: answers use approved salon information and recorded sample
          appointment slots. Booking and staff actions are not available.
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
            className={`voice-button ${listening ? "is-listening" : ""}`}
            type="button"
            aria-label={listening ? "Cancel voice input" : "Start voice input"}
            title={listening ? "Cancel voice input" : "Start voice input"}
            onClick={listening ? handleCancelVoice : handleStartVoice}
            disabled={!sessionActive || (busy && !listening)}
          >
            {listening ? "Cancel" : "Mic"}
          </button>
          <button
            className="send-button"
            type="submit"
            aria-label="Send message"
            disabled={!canCompose || !draft.trim()}
          >
            <span aria-hidden="true">↑</span>
          </button>
        </form>
        {voiceFeedback && (
          <div
            className={`voice-feedback ${voiceFeedbackIsError ? "voice-feedback-error" : ""}`}
            role={voiceFeedbackIsError ? "alert" : "status"}
            aria-live="polite"
          >
            <span>{voiceFeedback}</span>
            {speaking && (
              <button type="button" onClick={() => stopSpeech()}>
                Stop speech
              </button>
            )}
          </div>
        )}
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
