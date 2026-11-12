import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSession,
  endSession,
  getServices,
  getSessionStatus,
  safeErrorMessage,
  sendMessage,
} from "./api.js";
import ArchitecturePage from "./Architecture.jsx";

function toDisplayMessage(message) {
  return {
    id: message.message_id,
    sequence: message.sequence,
    role: message.role,
    text: message.text,
  };
}

function isHandoffConfirmationPrompt(text) {
  return (
    text === "Please say yes or no, or use the confirmation buttons." ||
    text === "I heard both yes and no. Would you like me to create a support ticket?" ||
    text.includes("Would you like me to create a queued support ticket for staff to follow up?")
  );
}

function getRecognitionErrorMessage(error) {
  const messages = {
    "audio-capture": "No microphone audio was detected. Check your microphone or type your message.",
    "not-allowed": "Microphone permission was denied. Allow microphone access or type your message.",
    "not-allowed-error": "Microphone permission was denied. Allow microphone access or type your message.",
    "service-not-allowed": "Speech recognition is blocked by the browser. You can type your message instead.",
    "no-speech": "No speech was recognized. Please try again or type your message.",
    network: "The browser reported a speech-recognition network error. Try again later or type your message.",
    aborted: "Voice input was cancelled.",
  };
  const errorCode = String(error ?? "")
    .replace(/([a-z])([A-Z])/g, "$1-$2")
    .toLowerCase();
  return messages[errorCode] ?? "Speech recognition failed. Please try again or type your message.";
}

function logRecognitionEvent(eventName, details = {}) {
  if (import.meta.env.DEV) {
    console.debug(`[speech-recognition] ${eventName}`, details);
  }
}

export default function App() {
  const [session, setSession] = useState(null);
  const [experience, setExperience] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [starting, setStarting] = useState(false);
  const [sending, setSending] = useState(false);
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [listening, setListening] = useState(false);
  const [recognitionStopping, setRecognitionStopping] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceFeedback, setVoiceFeedback] = useState("");
  const [voiceFeedbackIsError, setVoiceFeedbackIsError] = useState(false);
  const [interactionMode, setInteractionMode] = useState("mic");
  const [viewArchitecture, setViewArchitecture] = useState(false);
  const [liveCallTtsFinished, setLiveCallTtsFinished] = useState(false);
  const [servicesOpen, setServicesOpen] = useState(false);
  const [services, setServices] = useState([]);
  const [servicesLoading, setServicesLoading] = useState(false);
  const [servicesError, setServicesError] = useState("");
  const sendingRef = useRef(false);
  const startingRef = useRef(false);
  const recognitionRef = useRef(null);
  const recognitionStoppingRef = useRef(false);
  const voiceAttemptRef = useRef(0);
  const voiceSubmissionRef = useRef(false);
  const sessionRef = useRef(null);
  const observedSessionIdRef = useRef(null);
  const observedSessionStatusRef = useRef(null);
  const mountedRef = useRef(true);
  const transcriptRef = useRef(null);
  const inputRef = useRef(null);
  const liveCallRestartNeededRef = useRef(false);
  const liveCallStartRequestedRef = useRef(false);
  const liveCallNoSpeechRecoveryCountRef = useRef(0);
  const servicesLoadedRef = useRef(false);
  const servicesRequestRef = useRef(false);
  const browseServicesButtonRef = useRef(null);
  const closeServicesButtonRef = useRef(null);

  function abortRecognition(recognition = recognitionRef.current) {
    if (!recognition || recognitionStoppingRef.current) return;
    recognition.onresult = null;
    recognition.onerror = null;
    recognitionStoppingRef.current = true;
    setRecognitionStopping(true);
    recognition.onend = () => {
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
      recognitionStoppingRef.current = false;
      setRecognitionStopping(false);
    };
    recognition.abort();
  }

  function switchInteractionMode(nextMode) {
    if (
      !["message", "mic", "live"].includes(nextMode) ||
      nextMode === interactionMode
    ) {
      return;
    }

    voiceAttemptRef.current += 1;
    abortRecognition();
    voiceSubmissionRef.current = false;
    setListening(false);
    window.speechSynthesis?.cancel();
    setSpeaking(false);
    liveCallRestartNeededRef.current = false;
    liveCallStartRequestedRef.current =
      nextMode === "live" && sessionRef.current?.status === "active";
    liveCallNoSpeechRecoveryCountRef.current = 0;
    setLiveCallTtsFinished(false);
    setInteractionMode(nextMode);
    updateVoiceFeedback(
      nextMode === "live"
        ? "Switching to Live Call Mode."
        : "Voice listening stopped. Your conversation is unchanged.",
    );
  }

  function updateVoiceFeedback(message, { isError = false } = {}) {
    setVoiceFeedback(message);
    setVoiceFeedbackIsError(isError);
  }

  function cancelRecognition(message = "Voice input cancelled.") {
    voiceAttemptRef.current += 1;
    abortRecognition();
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

  const startConversation = useCallback(async (requestedMode = interactionMode) => {
    if (startingRef.current) return;
    setInteractionMode(requestedMode);
    voiceAttemptRef.current += 1;
    const previousRecognition = recognitionRef.current;
    if (previousRecognition) abortRecognition(previousRecognition);
    window.speechSynthesis?.cancel();
    voiceSubmissionRef.current = false;
    liveCallRestartNeededRef.current = false;
    liveCallNoSpeechRecoveryCountRef.current = 0;
    setListening(false);
    setSpeaking(false);
    setVoiceFeedback("");
    setVoiceFeedbackIsError(false);
    liveCallStartRequestedRef.current = requestedMode === "live";
    setLiveCallTtsFinished(false);
    startingRef.current = true;
    setStarting(true);
    setError("");
    setNotice("");

    try {
      const result = await createSession(
        requestedMode === "live" ? "browser_voice" : "text_web",
      );
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
      liveCallStartRequestedRef.current = false;
      setError(safeErrorMessage(requestError, "start a conversation"));
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
  }, [interactionMode]);

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
    if (
      previousSessionId &&
      currentSessionId !== previousSessionId &&
      observedSessionStatusRef.current === "active"
    ) {
      cancelRecognition("Voice input stopped because the conversation changed.");
      stopSpeech("Speech playback stopped because the conversation changed.");
    }
    observedSessionIdRef.current = currentSessionId;
    observedSessionStatusRef.current = session?.status ?? null;
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
  const callState = ending
    ? "ending"
    : session?.status === "closed"
      ? "ended"
      : sessionActive
        ? "active"
        : "idle";
  const callActive = callState === "active";

  useEffect(() => {
    if (servicesOpen) closeServicesButtonRef.current?.focus();
  }, [servicesOpen]);

  useEffect(() => {
    if (!liveCallStartRequestedRef.current || recognitionStopping) return;
    if (starting) return;
    if (session?.status === "closed") {
      liveCallStartRequestedRef.current = false;
      return;
    }
    if (!callActive || busy || interactionMode !== "live" || listening) return;
    liveCallStartRequestedRef.current = false;
    handleStartVoiceLiveCall();
  }, [
    callActive,
    busy,
    interactionMode,
    listening,
    recognitionStopping,
    session?.status,
    starting,
  ]);

  useEffect(() => {
    if (!liveCallTtsFinished) return;
    if (
      !liveCallRestartNeededRef.current ||
      interactionMode !== "live" ||
      !callActive
    ) {
      liveCallRestartNeededRef.current = false;
      setLiveCallTtsFinished(false);
      return;
    }
    if (busy || listening) return;
    liveCallRestartNeededRef.current = false;
    setLiveCallTtsFinished(false);
    handleStartVoiceLiveCall();
  }, [liveCallTtsFinished, interactionMode, callActive, busy, listening]);

  async function submitMessage(text, { speakResponse = false, sessionId, modality = "text", language, asrConfidence, voiceAttemptId } = {}) {
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
        channelType: sessionRef.current.channel_type,
        text: messageText,
        modality,
        language,
        asrConfidence,
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
      if (
        speakResponse &&
        sessionRef.current?.status === "active" &&
        (voiceAttemptId === undefined || voiceAttemptId === voiceAttemptRef.current)
      ) {
        speakAssistantResponse(
          result.assistant_message.text,
          targetSessionId,
          voiceAttemptId,
        );
      }
      return true;
    } catch (requestError) {
      if (!mountedRef.current) return false;
      if (requestError.status === 404 || requestError.status === 409) {
        const closedSession = { ...sessionRef.current, status: "closed" };
        sessionRef.current = closedSession;
        setSession(closedSession);
      }
      if (voiceAttemptId === voiceAttemptRef.current) {
        liveCallRestartNeededRef.current = false;
        setLiveCallTtsFinished(false);
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

  async function loadServices() {
    if (servicesLoadedRef.current || servicesRequestRef.current) return;
    servicesRequestRef.current = true;
    setServicesLoading(true);
    setServicesError("");
    try {
      const loadedServices = await getServices();
      setServices(loadedServices);
      servicesLoadedRef.current = true;
    } catch (requestError) {
      setServicesError(safeErrorMessage(requestError, "load services"));
    } finally {
      servicesRequestRef.current = false;
      setServicesLoading(false);
    }
  }

  function closeServicesPanel() {
    setServicesOpen(false);
    browseServicesButtonRef.current?.focus();
  }

  async function handleServiceSelection(service) {
    const submitted = await submitMessage(
      `What is the price and duration of ${service.name}?`,
    );
    if (submitted) closeServicesPanel();
  }

  function speakAssistantResponse(text, sessionId, voiceAttemptId) {
    if (!text?.trim()) {
      liveCallRestartNeededRef.current = false;
      updateVoiceFeedback("The assistant returned no text to speak.");
      return;
    }
    if (!window.speechSynthesis || typeof window.SpeechSynthesisUtterance !== "function") {
      liveCallRestartNeededRef.current = false;
      updateVoiceFeedback(
        "Voice reply is unavailable in this browser. The assistant response is shown above.",
        { isError: experience === "call-only" },
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
        sessionRef.current?.session_id === sessionId &&
        sessionRef.current?.status === "active" &&
        (voiceAttemptId === undefined || voiceAttemptId === voiceAttemptRef.current)
      ) {
        setSpeaking(true);
      }
    };
    utterance.onend = () => {
      if (
        mountedRef.current &&
        sessionRef.current?.session_id === sessionId &&
        sessionRef.current?.status === "active" &&
        (voiceAttemptId === undefined || voiceAttemptId === voiceAttemptRef.current)
      ) {
        setSpeaking(false);
        updateVoiceFeedback("Voice reply finished.");
        if (interactionMode === "live" && liveCallRestartNeededRef.current) {
          setLiveCallTtsFinished(true);
        }
      }
    };
    utterance.onerror = (event) => {
      if (
        !mountedRef.current ||
        sessionRef.current?.session_id !== sessionId ||
        sessionRef.current?.status !== "active" ||
        (voiceAttemptId !== undefined && voiceAttemptId !== voiceAttemptRef.current)
      ) {
        return;
      }
      liveCallRestartNeededRef.current = false;
      setLiveCallTtsFinished(false);
      setSpeaking(false);
      if (event.error === "canceled" || event.error === "interrupted") {
        updateVoiceFeedback("Speech playback stopped.");
      } else {
        updateVoiceFeedback(
          "The assistant response is shown above, but speech playback failed.",
          { isError: true },
        );
      }
    };
    window.speechSynthesis.speak(utterance);
  }

  function handleStartVoice() {
    if (
      !callActive ||
      busy ||
      listening ||
      recognitionStopping ||
      recognitionStoppingRef.current ||
      recognitionRef.current
    ) return;

    if (interactionMode === "live") {
      return handleStartVoiceLiveCall();
    }
    if (interactionMode !== "mic") return;

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      updateVoiceFeedback(
        "Voice input is not supported in this browser. You can type your message instead.",
        { isError: true },
      );
      return;
    }
    const sessionId = session.session_id;
    const attemptId = ++voiceAttemptRef.current;
    voiceSubmissionRef.current = false;
    setListening(true);
    setError("");
    updateVoiceFeedback("Starting speech recognition…");

    const recognition = new SpeechRecognition();
    let recognitionFailed = false;
    let recognitionErrorCode = null;
    let latestTranscript = "";
    let latestConfidence = null;

    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognitionRef.current = recognition;

    recognition.onstart = () => {
      logRecognitionEvent("start", { mode: "mic" });
      if (attemptId === voiceAttemptRef.current && mountedRef.current) {
        updateVoiceFeedback("Listening… Speak now, or cancel voice input.");
      }
    };
    recognition.onresult = (event) => {
      if (attemptId !== voiceAttemptRef.current || voiceSubmissionRef.current) return;

      const anyTranscript = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (anyTranscript) {
        latestTranscript = anyTranscript;
        const lastResult = event.results[event.results.length - 1];
        latestConfidence = lastResult?.[0]?.confidence ?? null;
      }

      const finalResults = Array.from(event.results).filter((result) => result.isFinal);
      logRecognitionEvent("result", {
        mode: "mic",
        resultCount: event.results.length,
        finalCount: finalResults.length,
      });
      const transcript = finalResults
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (!transcript) return;

      const lastFinal = finalResults[finalResults.length - 1];
      const asrConfidence = lastFinal?.[0]?.confidence ?? null;
      voiceSubmissionRef.current = true;
      setDraft(transcript);
      updateVoiceFeedback("Speech recognized. Sending your message…");
      recognition.stop();

      void submitMessage(transcript, {
        speakResponse: true,
        sessionId,
        modality: "speech_transcript",
        language: "en-US",
        asrConfidence,
        voiceAttemptId: attemptId,
      });
    };
    recognition.onerror = (event) => {
      logRecognitionEvent("error", { mode: "mic", error: event.error });
      recognitionFailed = true;
      recognitionErrorCode = event.error;
      if (attemptId !== voiceAttemptRef.current || !mountedRef.current) return;
      setListening(false);
      voiceSubmissionRef.current = false;
      liveCallRestartNeededRef.current = false;
      setLiveCallTtsFinished(false);
      if (event.error !== "no-speech") {
        updateVoiceFeedback(getRecognitionErrorMessage(event.error), { isError: true });
      }
      inputRef.current?.focus();
    };
    recognition.onend = () => {
      logRecognitionEvent("end", { mode: "mic" });
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
      if (attemptId !== voiceAttemptRef.current || !mountedRef.current) return;
      setListening(false);

      if (!voiceSubmissionRef.current) {
        if (latestTranscript && (!recognitionFailed || recognitionErrorCode === "no-speech")) {
          voiceSubmissionRef.current = true;
          setDraft(latestTranscript);
          updateVoiceFeedback("Speech recognized. Sending your message…");
          void submitMessage(latestTranscript, {
            speakResponse: true,
            sessionId,
            modality: "speech_transcript",
            language: "en-US",
            asrConfidence: latestConfidence,
            voiceAttemptId: attemptId,
          });
          return;
        }

        if (!recognitionFailed || recognitionErrorCode === "no-speech") {
          updateVoiceFeedback(
            "No speech was recognized. Please try again or type your message.",
            { isError: true },
          );
        }
      }
    };

    try {
      recognition.start();
      logRecognitionEvent("start-requested", { mode: "mic" });
    } catch (recognitionError) {
      recognitionRef.current = null;
      setListening(false);
      liveCallRestartNeededRef.current = false;
      setLiveCallTtsFinished(false);
      updateVoiceFeedback(getRecognitionErrorMessage(recognitionError.name), { isError: true });
    }
  }

  function handleStartVoiceLiveCall() {
    if (
      !callActive ||
      busy ||
      listening ||
      recognitionStopping ||
      recognitionStoppingRef.current ||
      recognitionRef.current ||
      interactionMode !== "live"
    ) return;

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      updateVoiceFeedback(
        "Voice input is not supported in this browser. You can type your message instead.",
        { isError: true },
      );
      return;
    }

    const sessionId = session.session_id;
    const attemptId = ++voiceAttemptRef.current;
    voiceSubmissionRef.current = false;
    setListening(true);
    setError("");
    updateVoiceFeedback("Starting speech recognition…");

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognitionRef.current = recognition;

    let liveCallAttemptId = attemptId;
    let recognitionFailed = false;
    let recognitionErrorCode = null;
    let latestTranscript = "";
    let latestConfidence = null;

    recognition.onstart = () => {
      logRecognitionEvent("start", { mode: "live-call" });
      if (liveCallAttemptId === voiceAttemptRef.current && mountedRef.current) {
        updateVoiceFeedback("Listening… Speak now.");
      }
    };
    recognition.onresult = (event) => {
      if (liveCallAttemptId !== voiceAttemptRef.current || voiceSubmissionRef.current) return;

      const anyTranscript = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (anyTranscript) {
        latestTranscript = anyTranscript;
        const lastResult = event.results[event.results.length - 1];
        latestConfidence = lastResult?.[0]?.confidence ?? null;
      }

      const finalResults = Array.from(event.results).filter((result) => result.isFinal);
      logRecognitionEvent("result", {
        mode: "live-call",
        resultCount: event.results.length,
        finalCount: finalResults.length,
      });
      const transcript = finalResults
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (!transcript) return;

      const lastFinal = finalResults[finalResults.length - 1];
      const asrConfidence = lastFinal?.[0]?.confidence ?? null;

      voiceSubmissionRef.current = true;
      liveCallNoSpeechRecoveryCountRef.current = 0;
      setDraft(transcript);
      updateVoiceFeedback("Speech recognized. Sending your message…");
      recognition.stop();

      setLiveCallTtsFinished(false);
      liveCallRestartNeededRef.current = true;

      void submitMessage(transcript, {
        speakResponse: true,
        sessionId,
        modality: "speech_transcript",
        language: "en-US",
        asrConfidence,
        voiceAttemptId: liveCallAttemptId,
      }).then((submitted) => {
        if (!submitted && liveCallAttemptId === voiceAttemptRef.current) {
          liveCallRestartNeededRef.current = false;
          setLiveCallTtsFinished(false);
        }
      });
    };

    recognition.onerror = (event) => {
      logRecognitionEvent("error", { mode: "live-call", error: event.error });
      recognitionFailed = true;
      recognitionErrorCode = event.error;
      if (liveCallAttemptId !== voiceAttemptRef.current || !mountedRef.current) return;
      setListening(false);
      voiceSubmissionRef.current = false;
      liveCallRestartNeededRef.current = false;
      setLiveCallTtsFinished(false);
      if (event.error !== "no-speech") {
        updateVoiceFeedback(getRecognitionErrorMessage(event.error), { isError: true });
      }
      inputRef.current?.focus();
    };

    recognition.onend = () => {
      logRecognitionEvent("end", { mode: "live-call" });
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
      if (liveCallAttemptId !== voiceAttemptRef.current || !mountedRef.current) return;
      setListening(false);

      if (!voiceSubmissionRef.current) {
        if (latestTranscript && (!recognitionFailed || recognitionErrorCode === "no-speech")) {
          voiceSubmissionRef.current = true;
          liveCallNoSpeechRecoveryCountRef.current = 0;
          setDraft(latestTranscript);
          updateVoiceFeedback("Speech recognized. Sending your message…");
          setLiveCallTtsFinished(false);
          liveCallRestartNeededRef.current = true;

          void submitMessage(latestTranscript, {
            speakResponse: true,
            sessionId,
            modality: "speech_transcript",
            language: "en-US",
            asrConfidence: latestConfidence,
            voiceAttemptId: liveCallAttemptId,
          }).then((submitted) => {
            if (!submitted && liveCallAttemptId === voiceAttemptRef.current) {
              liveCallRestartNeededRef.current = false;
              setLiveCallTtsFinished(false);
            }
          });
          return;
        }

        if (!recognitionFailed || recognitionErrorCode === "no-speech") {
          if (liveCallNoSpeechRecoveryCountRef.current < 3) {
            liveCallNoSpeechRecoveryCountRef.current += 1;
            liveCallStartRequestedRef.current = true;
            updateVoiceFeedback("No speech was recognized. Listening again.");
          } else {
            updateVoiceFeedback(
              "No speech was recognized. Please speak again or type your message.",
              { isError: true },
            );
          }
        }
      }
    };

    try {
      recognition.start();
      logRecognitionEvent("start-requested", { mode: "live-call" });
    } catch (recognitionError) {
      recognitionRef.current = null;
      setListening(false);
      liveCallRestartNeededRef.current = false;
      setLiveCallTtsFinished(false);
      updateVoiceFeedback(getRecognitionErrorMessage(recognitionError.name), { isError: true });
    }
  }

  function handleCancelVoice() {
    cancelRecognition();
  }

  function handleSubmit(event) {
    event.preventDefault();
    void submitMessage(draft);
  }

  async function handleEndConversation() {
    if (!callActive || ending) return;
    liveCallStartRequestedRef.current = false;
    liveCallRestartNeededRef.current = false;
    setLiveCallTtsFinished(false);
    cancelRecognition("Voice input stopped because the conversation is ending.");
    stopSpeech("Speech playback stopped because the conversation is ending.");
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

  function startCallOnly() {
    setExperience("call-only");
    void startConversation("live");
  }

  function returnToExperienceSelection() {
    if (callActive || ending || starting) return;
    setExperience(null);
    setError("");
    setNotice("");
    setVoiceFeedback("");
    setVoiceFeedbackIsError(false);
  }

  const canCompose = callActive && !busy && !listening;

  if (viewArchitecture) {
    return (
      <ArchitecturePage onBack={() => setViewArchitecture(false)} />
    );
  }

  if (!experience) {
    return (
      <main className="page-shell">
        <header className="site-header">
          <a className="wordmark" href="/" aria-label="TECHOHUB home">
            <span className="wordmark-mark" aria-hidden="true">T</span>
            <span>TECHOHUB<span className="wordmark-period">.</span></span>
          </a>
          <span className="header-label">CUSTOMER CARE DEMO</span>
        </header>
        <section className="experience-picker" aria-labelledby="experience-title">
          <p className="eyebrow">DEMO SALON</p>
          <h1 id="experience-title">Choose how you’d like to talk</h1>
          <p>Both experiences use the same assistant and approved salon information.</p>
          <div className="experience-options">
            <button
              type="button"
              onClick={() => setExperience("multimodal")}
            >
              <strong>Multimodal Assistant</strong>
              <span>Chat, use your microphone, or switch to Live Call Mode.</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setError("");
                setNotice("");
                setVoiceFeedback("");
                setVoiceFeedbackIsError(false);
                setExperience("call-only");
              }}
            >
              <strong>Call-Only Assistant</strong>
              <span>Have a speech-first conversation with spoken replies.</span>
            </button>
            <button
              type="button"
              className="experience-cta"
              onClick={() => setViewArchitecture(true)}
            >
              <span>View how TECHOHUB works</span>
              <span className="experience-cta-sub">System architecture &amp; workflow</span>
            </button>
          </div>
          <p className="experience-note">
            Call-Only is a browser voice experience, not a telephone call.
          </p>
        </section>
        <footer className="page-footer">
          <span>TECHOHUB · Academic prototype</span>
        </footer>
      </main>
    );
  }

  if (experience === "call-only") {
    const callOnlyStatus = starting
      ? "Starting call…"
      : ending
        ? "Ending call…"
        : callState === "active"
          ? speaking
            ? "Assistant speaking"
            : sending
              ? "Processing your message"
              : listening
                ? "Listening"
                : voiceFeedbackIsError
                  ? "Voice service needs attention"
                  : "Call active"
          : callState === "ended"
            ? "Call ended"
            : "Ready to call";

    return (
      <main className="page-shell">
        <header className="site-header">
          <a className="wordmark" href="/" aria-label="TECHOHUB home">
            <span className="wordmark-mark" aria-hidden="true">T</span>
            <span>TECHOHUB<span className="wordmark-period">.</span></span>
          </a>
          <span className="header-label">CALL-ONLY DEMO</span>
        </header>
        <section className="call-only-panel" aria-labelledby="call-only-title">
          <div className="assistant-avatar" aria-hidden="true">T</div>
          <p className="eyebrow">DEMO SALON</p>
          <h1 id="call-only-title">Call-Only Assistant</h1>
          <p className="call-only-description">
            {callActive
              ? "Speak naturally after the assistant finishes. Your conversation is handled by the same TECHOHUB assistant."
              : "Start a browser voice conversation. No chat controls are needed."}
          </p>
          <p className="call-only-status" role="status" aria-live="polite">
            <span className={`status-dot ${callActive ? "is-online" : ""}`} />
            {callOnlyStatus}
          </p>
          {error && <p className="call-only-error" role="alert">{error}</p>}
          {voiceFeedback && (
            <p
              className={`call-only-feedback ${voiceFeedbackIsError ? "is-error" : ""}`}
              role={voiceFeedbackIsError ? "alert" : "status"}
              aria-live="polite"
            >
              {voiceFeedback}
            </p>
          )}
          {notice && <p className="call-only-feedback" role="status">{notice}</p>}
          <div className="call-only-actions">
            {callActive ? (
              <>
                {voiceFeedbackIsError && !listening && !sending && !ending && (
                  <button
                    className="call-only-secondary-button"
                    type="button"
                    onClick={() => {
                      liveCallNoSpeechRecoveryCountRef.current = 0;
                      handleStartVoiceLiveCall();
                    }}
                    disabled={recognitionStopping || Boolean(recognitionRef.current)}
                  >
                    Retry listening
                  </button>
                )}
                <button
                  className="call-only-end-button"
                  type="button"
                  onClick={handleEndConversation}
                  disabled={ending || starting}
                >
                  End Call
                </button>
              </>
            ) : (
              <>
                <button
                  className="call-only-start-button"
                  type="button"
                  onClick={() => void startConversation("live")}
                  disabled={starting || ending || recognitionStopping}
                >
                  {callState === "ended" ? "Call Again" : "Start Call"}
                </button>
                <button
                  className="call-only-secondary-button"
                  type="button"
                  onClick={returnToExperienceSelection}
                  disabled={starting || ending}
                >
                  Choose another experience
                </button>
              </>
            )}
          </div>
          <p className="call-only-note">
            Browser speech recognition and speech playback are required. This is not a telephone service.
          </p>
        </section>
        <footer className="page-footer">
          <span>TECHOHUB · Academic prototype</span>
        </footer>
      </main>
    );
  }

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
              <span
                className={`status-dot ${callActive ? "is-online" : ""}`}
              />
              {starting
                ? "Connecting..."
                : interactionMode === "live" && callActive
                  ? speaking
                    ? "Speaking"
                    : sending
                      ? "Processing"
                      : listening
                        ? "Listening"
                        : voiceFeedbackIsError
                          ? "Voice error"
                          : "Call active"
                : callState === "active"
                  ? "Call active"
                  : callState === "ended"
                    ? "Call ended"
                    : "Idle"}
            </p>
          </div>
          {(callState === "active" || callState === "ending") && (
            <button
              className="end-button"
              type="button"
              onClick={handleEndConversation}
              disabled={ending || starting}
            >
              End Call
            </button>
          )}
          </div>

          {(callState === "active" || callState === "idle" || callState === "ended") && (
            <div className="mode-selector-wrapper">
              <div className="mode-selector" role="radiogroup" aria-label="Conversation mode">
                <label>
                  <input
                    type="radio"
                    name="voice-mode"
                    value="message"
                    checked={interactionMode === "message"}
                    onChange={() => switchInteractionMode("message")}
                    disabled={starting || ending}
                  />
                  Message Mode
                </label>
                <label>
                  <input
                    type="radio"
                    name="voice-mode"
                    value="mic"
                    checked={interactionMode === "mic"}
                    onChange={() => switchInteractionMode("mic")}
                    disabled={starting || ending}
                  />
                  Mic Mode
                </label>
                <label>
                  <input
                    type="radio"
                    name="voice-mode"
                    value="live"
                    checked={interactionMode === "live"}
                    onChange={() => switchInteractionMode("live")}
                    disabled={starting || ending}
                  />
                  Live Call Mode
                </label>
              </div>
              {(callState === "idle" || callState === "ended") && (
                <button
                  className="start-button"
                  type="button"
                  onClick={() => void startConversation()}
                  disabled={busy || starting}
                >
                  Start Call
                </button>
              )}
            </div>
          )}

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

        <div className="browse-services-toolbar">
          <button
            ref={browseServicesButtonRef}
            className="browse-services-button"
            type="button"
            onClick={() => {
              setServicesOpen(true);
              void loadServices();
            }}
          >
            Browse Services
          </button>
        </div>

        {servicesOpen && (
          <section
            className="services-panel"
            role="dialog"
            aria-labelledby="services-panel-title"
            onKeyDown={(event) => {
              if (event.key === "Escape") closeServicesPanel();
            }}
          >
            <div className="services-panel-heading">
              <h2 id="services-panel-title">Available services</h2>
              <button
                ref={closeServicesButtonRef}
                className="services-close-button"
                type="button"
                onClick={closeServicesPanel}
                aria-label="Close services"
              >
                Close
              </button>
            </div>
            {servicesLoading && (
              <p className="services-state" role="status">Loading services…</p>
            )}
            {servicesError && (
              <div className="services-state services-error" role="alert">
                <span>{servicesError}</span>
                <button type="button" onClick={() => void loadServices()}>
                  Try again
                </button>
              </div>
            )}
            {!servicesLoading && !servicesError && servicesLoadedRef.current && services.length === 0 && (
              <p className="services-state" role="status">
                No services are currently available.
              </p>
            )}
            {!servicesLoading && !servicesError && services.length > 0 && (
              <div className="service-cards">
                {services.map((service) => (
                  <button
                    className="service-card"
                    key={service.service_id}
                    type="button"
                    onClick={() => void handleServiceSelection(service)}
                    disabled={!callActive || busy || listening}
                  >
                    <span className="service-card-name">{service.name}</span>
                    <span>
                      {new Intl.NumberFormat(undefined, {
                        style: "currency",
                        currency: service.currency,
                      }).format(Number(service.price_amount))}
                      {" · "}
                      {service.duration_minutes} minutes
                    </span>
                    {!callActive && (
                      <span className="service-card-hint">
                        Start a conversation to ask about this service.
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </section>
        )}

        <div
          className="transcript"
          role="log"
          aria-label="Conversation"
          aria-live="polite"
          aria-relevant="additions text"
          ref={transcriptRef}
        >
          {messages.map((message, index) => (
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
                {index === messages.length - 1 &&
                  message.role === "assistant" &&
                  isHandoffConfirmationPrompt(message.text) && (
                    <div className="handoff-actions" aria-label="Ticket confirmation">
                      <button
                        type="button"
                        onClick={() => void submitMessage("yes")}
                        disabled={!callActive || busy}
                      >
                        Yes, create ticket
                      </button>
                      <button
                        type="button"
                        onClick={() => void submitMessage("no")}
                        disabled={!callActive || busy}
                      >
                        No, thanks
                      </button>
                    </div>
                  )}
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
          </div>
        )}
        {notice && (
          <div className="feedback feedback-notice" role="status">
            <span>{notice}</span>
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
            placeholder={callActive ? "Write a message…" : "Call is unavailable"}
            rows={1}
            maxLength={2000}
            disabled={!canCompose}
            aria-describedby="composer-help"
          />
          {interactionMode === "mic" && (
            <button
              className={`voice-button ${listening ? "is-listening" : ""}`}
              type="button"
              aria-label={listening ? "Cancel voice input" : "Start voice input"}
              title={listening ? "Cancel voice input" : "Start voice input"}
              onClick={listening ? handleCancelVoice : handleStartVoice}
              disabled={!callActive || (busy && !listening)}
            >
              {listening ? "Cancel" : "Mic"}
            </button>
          )}
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
