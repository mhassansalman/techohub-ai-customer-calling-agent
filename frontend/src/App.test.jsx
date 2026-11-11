import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App.jsx";

function sessionPayload(
  status = "active",
  channelType = "text_web",
  sessionId = SESSION_ID,
) {
  return {
    session_id: sessionId,
    channel_type: channelType,
    status,
    started_at: "2026-10-25T08:00:00Z",
    ended_at: null,
    outcome: null,
    message_count: 1,
    audit_event_count: 1,
  };
}

const SESSION_ID = "1608b129-9ab8-46f7-9dd7-6fb2a4b216fc";
const interim =
  "Your message was recorded. Automated response generation is not implemented yet.";

function messagePayload({ id, role, sequence, text, sessionId = SESSION_ID }) {
  return {
    message_id: id,
    session_id: sessionId,
    sequence,
    role,
    text,
    timestamp: "2026-10-25T08:01:00Z",
    modality: role === "assistant" ? "text" : "text",
  };
}

function mockApi({
  sendDelay,
  sendStatus,
  statusStatus,
  assistantText = interim,
  serviceDelay,
  servicesStatus,
  servicesList = [
    {
      service_id: "haircut",
      name: "Haircut",
      price_amount: "35.00",
      currency: "USD",
      duration_minutes: 30,
    },
    {
      service_id: "beard-trim",
      name: "Beard trim",
      price_amount: "18.00",
      currency: "USD",
      duration_minutes: 20,
    },
  ],
} = {}) {
  const calls = [];
  let messageNumber = 0;
  let sessionNumber = 0;
  const sessions = new Map();
  // Direct globalThis.fetch assignment (no vi.stubGlobal) for jsdom compatibility
  globalThis.fetch = vi.fn(async (url, options = {}) => {
    calls.push({ url, options });
    if (url === "/api/services" && !options.method) {
      if (serviceDelay) await serviceDelay;
      if (servicesStatus) {
        return new Response(JSON.stringify({ detail: "private backend detail" }), {
          status: servicesStatus,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(servicesList), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url === "/api/sessions" && options.method === "POST") {
      sessionNumber += 1;
      const sessionId =
        sessionNumber === 1
          ? SESSION_ID
          : `2608b129-9ab8-46f7-9dd7-${String(sessionNumber).padStart(12, "0")}`;
      const sessionChannel = JSON.parse(options.body).channel_type;
      sessions.set(sessionId, { ended: false, channel: sessionChannel });
      return new Response(
        JSON.stringify({
          session: sessionPayload("active", sessionChannel, sessionId),
          assistant_disclosure:
            "I am an automated assistant. Typed messages and recognized speech transcripts are stored to support the conversation. Microphone audio is not stored.",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    }
    const sessionRoute = url.match(/^\/api\/sessions\/([^/]+)(?:\/(messages|end))?$/);
    if (sessionRoute && !options.method && !sessionRoute[2]) {
      const [, sessionId] = sessionRoute;
      const currentSession = sessions.get(sessionId);
      if (!currentSession) {
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }
      if (statusStatus) {
        return new Response(JSON.stringify({ detail: "private backend detail" }), {
          status: statusStatus,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(sessionPayload(
        currentSession.ended ? "closed" : "active",
        currentSession.channel,
        sessionId,
      )), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (sessionRoute && sessionRoute[2] === "messages") {
      if (sendDelay) {
        await (Array.isArray(sendDelay) ? sendDelay.shift() : sendDelay);
      }
      if (sendStatus) {
        return new Response(JSON.stringify({ detail: "internal stack trace" }), {
          status: sendStatus,
          headers: { "Content-Type": "application/json" },
        });
      }
      messageNumber += 1;
      const [, sessionId] = sessionRoute;
      const payload = JSON.parse(options.body);
      const responseText = Array.isArray(assistantText)
        ? assistantText[Math.min(messageNumber - 1, assistantText.length - 1)]
        : assistantText;
      return new Response(
        JSON.stringify({
          customer_message: messagePayload({
            id: `customer-${messageNumber}`,
            role: "customer",
            sequence: messageNumber * 2,
            text: payload.message_text,
            sessionId,
          }),
          assistant_message: messagePayload({
            id: `assistant-${messageNumber}`,
            role: "assistant",
            sequence: messageNumber * 2 + 1,
            text: responseText,
            sessionId,
          }),
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (sessionRoute && sessionRoute[2] === "end") {
      const [, sessionId] = sessionRoute;
      const currentSession = sessions.get(sessionId);
      if (!currentSession) {
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }
      currentSession.ended = true;
      return new Response(JSON.stringify(sessionPayload(
        "closed",
        currentSession.channel,
        sessionId,
      )), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected API request: ${options.method} ${url}`);
  });
  return calls;
}

function mockVoice({ endUtteranceImmediately = false, deferAbort = false } = {}) {
  vi.spyOn(console, "debug").mockImplementation(() => {});
  const recognitions = [];
  const utterances = [];

  class MockSpeechRecognition {
    start = vi.fn(() => this.onstart?.());
    stop = vi.fn(() => this.onend?.());
    abort = vi.fn(() => {
      if (!deferAbort) this.onend?.();
    });

    constructor() {
      recognitions.push(this);
    }
  }

  class MockSpeechSynthesisUtterance {
    constructor(text) {
      this.text = text;
      utterances.push(this);
    }
  }

  const synthesis = {
    cancel: vi.fn(),
    speak: vi.fn((utterance) => {
      utterance.onstart?.();
      if (endUtteranceImmediately) utterance.onend?.();
    }),
  };

  Object.defineProperty(window, "SpeechRecognition", {
    configurable: true,
    value: MockSpeechRecognition,
  });
  Object.defineProperty(window, "webkitSpeechRecognition", {
    configurable: true,
    value: undefined,
  });
  Object.defineProperty(window, "SpeechSynthesisUtterance", {
    configurable: true,
    value: MockSpeechSynthesisUtterance,
  });
  Object.defineProperty(window, "speechSynthesis", {
    configurable: true,
    value: synthesis,
  });
  return {
    recognitions,
    utterances,
    synthesis,
    SpeechRecognition: MockSpeechRecognition,
  };
}

function emitRecognitionResult(recognition, transcript, isFinal = true, confidence) {
  recognition.onresult({
    results: [{ 0: { transcript, confidence }, isFinal }],
  });
}

async function waitForReady({ liveCallMode = false, mode } = {}) {
  const multimodalChoice = await screen.findByRole("button", {
    name: /Multimodal Assistant/,
  });
  fireEvent.click(multimodalChoice);
  const startCallButton = await screen.findByRole("button", { name: "Start Call" });
  const startingMode = liveCallMode ? "live" : mode;
  if (startingMode) {
    const labels = {
      message: "Message Mode",
      mic: "Mic Mode",
      live: "Live Call Mode",
    };
    fireEvent.click(screen.getByRole("radio", { name: labels[startingMode] }));
  }
  fireEvent.click(startCallButton);
  await screen.findByRole("button", { name: "End Call" });
  if (startingMode === "live") {
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Listening"),
    );
  } else {
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "Your message" })).toBeEnabled(),
    );
  }
}

async function waitForCallOnlyReady() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /Call-Only Assistant/ }));
  await user.click(screen.getByRole("button", { name: "Start Call" }));
  await screen.findByRole("button", { name: "End Call" });
  await waitFor(() =>
    expect(screen.getByText("Listening", { selector: ".call-only-status" })).toBeInTheDocument(),
  );
  return user;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Restore globalThis.fetch after each test to avoid mock leakage
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  // Reset globalThis.fetch to avoid interfering with other tests
  // (jsdom may not have fetch, so we just leave it as-is after restoration)
});

describe("Call-Only experience", () => {
  it("offers separate Multimodal and Call-Only experiences", async () => {
    mockApi();
    render(<App />);
    expect(await screen.findByRole("button", { name: /Multimodal Assistant/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Call-Only Assistant/ })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Your message" })).not.toBeInTheDocument();
  });

  it("starts a browser_voice session and hides all multimodal controls", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForCallOnlyReady();

    expect(JSON.parse(calls.find((call) => call.url === "/api/sessions").options.body))
      .toEqual({ channel_type: "browser_voice" });
    expect(voice.recognitions).toHaveLength(1);
    expect(screen.queryByRole("textbox", { name: "Your message" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Browse Services" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes, create ticket" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "No, thanks" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "End Call" })).toBeEnabled();
  });

  it("automatically listens, submits speech, speaks the answer, and listens again", async () => {
    const serviceAnswer = "A haircut costs $35 and takes about 30 minutes.";
    const availabilityAnswer = "I found a recorded appointment slot at 10 AM.";
    const calls = mockApi({ assistantText: [serviceAnswer, availabilityAnswer] });
    const voice = mockVoice();
    render(<App />);
    await waitForCallOnlyReady();

    emitRecognitionResult(voice.recognitions[0], "How much is a haircut?");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    expect(voice.utterances[0].text).toBe(serviceAnswer);
    expect(JSON.parse(calls.filter((call) => call.url.endsWith("/messages"))[0].options.body))
      .toMatchObject({
        channel_type: "browser_voice",
        modality: "speech_transcript",
        message_text: "How much is a haircut?",
      });
    expect(screen.queryByText(serviceAnswer)).not.toBeInTheDocument();

    voice.utterances[0].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    emitRecognitionResult(voice.recognitions[1], "Do you have an appointment on Friday?");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledTimes(2));
    expect(voice.utterances[1].text).toBe(availabilityAnswer);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(2);
  });

  it.each(["yes", "no", "okay", "yes no"])(
    "sends spoken handoff response %s through the existing message API",
    async (answer) => {
      const prompt =
        "Would you like me to create a queued support ticket for staff to follow up? Please reply yes or no.";
      const calls = mockApi({ assistantText: [prompt, "Your response was recorded."] });
      const voice = mockVoice();
      render(<App />);
      await waitForCallOnlyReady();
      emitRecognitionResult(voice.recognitions[0], "I need a human.");
      await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
      expect(voice.utterances[0].text).toBe(prompt);

      voice.utterances[0].onend();
      await waitFor(() => expect(voice.recognitions).toHaveLength(2));
      emitRecognitionResult(voice.recognitions[1], answer);
      await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledTimes(2));
      const messages = calls.filter((call) => call.url.endsWith("/messages"));
      expect(messages).toHaveLength(2);
      expect(JSON.parse(messages[1].options.body)).toMatchObject({
        channel_type: "browser_voice",
        modality: "speech_transcript",
        message_text: answer,
      });
      expect(screen.queryByRole("button", { name: "Yes, create ticket" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "No, thanks" })).not.toBeInTheDocument();
    },
  );

  it("shows a permission error and allows ending the call", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForCallOnlyReady();
    voice.recognitions[0].onerror({ error: "not-allowed" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Microphone permission was denied",
    );
    expect(screen.getByRole("button", { name: "End Call" })).toBeEnabled();
    await userEvent.setup().click(screen.getByRole("button", { name: "End Call" }));
    await waitFor(() => expect(calls.some((call) => call.url.endsWith("/end"))).toBe(true));
  });

  it("bounds silence recovery and allows an explicit listening retry", async () => {
    const voice = mockVoice();
    render(<App />);
    await waitForCallOnlyReady();

    voice.recognitions[0].onerror?.({ error: "no-speech" });
    voice.recognitions[0].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    voice.recognitions[1].onerror?.({ error: "no-speech" });
    voice.recognitions[1].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(3));
    voice.recognitions[2].onerror?.({ error: "no-speech" });
    voice.recognitions[2].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(3));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No speech was recognized. Please speak again or type your message.",
    );
    expect(voice.recognitions).toHaveLength(3);
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry listening" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(4));
  });

  it("cleans up speech on End Call, ignores stale TTS, and starts a fresh session", async () => {
    const calls = mockApi({ assistantText: "A voice response." });
    const voice = mockVoice();
    render(<App />);
    await waitForCallOnlyReady();
    emitRecognitionResult(voice.recognitions[0], "Hello assistant.");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    const oldUtterance = voice.utterances[0];

    await userEvent.setup().click(screen.getByRole("button", { name: "End Call" }));
    await screen.findByRole("button", { name: "Call Again" });
    expect(voice.synthesis.cancel).toHaveBeenCalled();
    oldUtterance.onend();
    expect(voice.recognitions).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Choose another experience" })).toBeEnabled();

    await userEvent.setup().click(screen.getByRole("button", { name: "Call Again" }));
    await waitFor(() => {
      expect(calls.filter((call) => call.url === "/api/sessions")).toHaveLength(2);
    });
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    expect(JSON.parse(calls.filter((call) => call.url === "/api/sessions")[1].options.body))
      .toEqual({ channel_type: "browser_voice" });
  });

  it("does not restart recognition after End Call while abort completion is delayed", async () => {
    const voice = mockVoice({ deferAbort: true });
    render(<App />);
    await waitForCallOnlyReady();
    const recognition = voice.recognitions[0];

    await userEvent.setup().click(screen.getByRole("button", { name: "End Call" }));
    await screen.findByRole("button", { name: "Call Again" });
    expect(recognition.abort).toHaveBeenCalledOnce();
    recognition.onend();
    expect(voice.recognitions).toHaveLength(1);
  });

  it("returns to the experience chooser after Call-Only ends", async () => {
    mockApi();
    mockVoice();
    render(<App />);
    await waitForCallOnlyReady();
    await userEvent.setup().click(screen.getByRole("button", { name: "End Call" }));
    await screen.findByRole("button", { name: "Choose another experience" });
    await userEvent.setup().click(screen.getByRole("button", {
      name: "Choose another experience",
    }));

    expect(await screen.findByRole("button", { name: /Multimodal Assistant/ }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Call-Only Assistant/ }))
      .toBeInTheDocument();
  });

  it("handles API error safely in Call-Only mode without invoking TTS and keeps End Call enabled", async () => {
    mockApi({ sendStatus: 500 });
    const voice = mockVoice();
    render(<App />);
    await waitForCallOnlyReady();
    emitRecognitionResult(voice.recognitions[0], "How much is a haircut?");

    expect(await screen.findByRole("alert")).toHaveTextContent("server error 500");
    expect(voice.synthesis.speak).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "End Call" })).toBeEnabled();
  });

  it("speaks booking limitation and unknown-service responses in Call-Only mode", async () => {
    const bookingDisclaimer =
      "I can check the recorded slots, but I can't book an appointment in this demo.";
    const unknownService =
      "Sorry, I don't have approved details for that service, so I can't confirm whether we offer it.";
    const calls = mockApi({ assistantText: [bookingDisclaimer, unknownService] });
    const voice = mockVoice();
    render(<App />);
    await waitForCallOnlyReady();

    emitRecognitionResult(voice.recognitions[0], "Book a haircut on Friday.");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    expect(voice.utterances[0].text).toBe(bookingDisclaimer);

    voice.utterances[0].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));

    emitRecognitionResult(voice.recognitions[1], "Do you offer hair coloring?");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledTimes(2));
    expect(voice.utterances[1].text).toBe(unknownService);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(2);
  });
});

describe("browser text chat", () => {
  it.each([
    ["message", "mic"],
    ["mic", "message"],
    ["message", "live"],
    ["live", "message"],
    ["mic", "live"],
    ["live", "mic"],
  ])("switches %s to %s without replacing the session or transcript", async (from, to) => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ mode: "message" });
    await user.type(screen.getByRole("textbox", { name: "Your message" }), "Conversation history");
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Conversation history")).toBeInTheDocument();

    if (from !== "message") {
      await user.click(screen.getByRole("radio", {
        name: from === "mic" ? "Mic Mode" : "Live Call Mode",
      }));
      if (from === "live") {
        await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Listening"));
      }
    }

    await user.click(screen.getByRole("radio", {
      name: { message: "Message Mode", mic: "Mic Mode", live: "Live Call Mode" }[to],
    }));
    expect(screen.getByRole("radio", {
      name: { message: "Message Mode", mic: "Mic Mode", live: "Live Call Mode" }[to],
    })).toBeChecked();
    expect(screen.getByText("Conversation history")).toBeInTheDocument();
    expect(screen.getByText(`Session ${SESSION_ID.slice(0, 8)}`)).toBeInTheDocument();
    expect(calls.filter((call) => call.url === "/api/sessions")).toHaveLength(1);
    if (to === "live") {
      await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Listening"));
      expect(voice.recognitions.length).toBeGreaterThan(0);
    }
  });

  it("aborts listening and ignores stale recognition callbacks when switching modes", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    const originalRecognition = voice.recognitions[0];
    const staleResult = originalRecognition.onresult;
    const staleEnd = originalRecognition.onend;

    await user.click(screen.getByRole("radio", { name: "Message Mode" }));
    expect(originalRecognition.abort).toHaveBeenCalledOnce();
    staleResult({
      results: [{ 0: { transcript: "stale speech" }, isFinal: true }],
    });
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);

    await user.click(screen.getByRole("radio", { name: "Live Call Mode" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    staleEnd();
    expect(voice.recognitions).toHaveLength(2);
  });

  it("aborts an active Mic utterance when switching to Message Mode", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    const recognition = voice.recognitions[0];

    await user.click(screen.getByRole("radio", { name: "Message Mode" }));

    expect(recognition.abort).toHaveBeenCalledOnce();
    expect(screen.getByRole("textbox", { name: "Your message" })).toBeEnabled();
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
  });

  it("replaces a listening Mic cycle with exactly one Live Call cycle", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    const micRecognition = voice.recognitions[0];
    const staleEnd = micRecognition.onend;

    await user.click(screen.getByRole("radio", { name: "Live Call Mode" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    expect(micRecognition.abort).toHaveBeenCalledOnce();
    expect(voice.recognitions[1].start).toHaveBeenCalledOnce();
    staleEnd();
    expect(voice.recognitions).toHaveLength(2);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
  });

  it("waits for asynchronous recognition abort before starting Live Call", async () => {
    const voice = mockVoice({ deferAbort: true });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    const micRecognition = voice.recognitions[0];

    await user.click(screen.getByRole("radio", { name: "Live Call Mode" }));
    expect(micRecognition.abort).toHaveBeenCalledOnce();
    expect(voice.recognitions).toHaveLength(1);

    micRecognition.onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    expect(voice.recognitions[1].start).toHaveBeenCalledOnce();
  });

  it("cancels TTS on a mode switch without triggering a Live Call restart", async () => {
    const calls = mockApi({ assistantText: "A spoken response." });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    emitRecognitionResult(voice.recognitions[0], "Ask by voice");
    await screen.findByText("A spoken response.");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    const utterance = voice.utterances[0];

    await user.click(screen.getByRole("radio", { name: "Message Mode" }));
    expect(voice.synthesis.cancel).toHaveBeenCalled();
    utterance.onend();
    expect(voice.recognitions).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1);
  });

  it("switches away from Live Call TTS without restarting recognition", async () => {
    mockApi({ assistantText: "A live spoken response." });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    emitRecognitionResult(voice.recognitions[0], "Ask in Live Call");
    await screen.findByText("A live spoken response.");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    const utterance = voice.utterances[0];

    await user.click(screen.getByRole("radio", { name: "Mic Mode" }));
    expect(voice.synthesis.cancel).toHaveBeenCalled();
    utterance.onend();
    expect(voice.recognitions).toHaveLength(1);
    expect(screen.getByRole("radio", { name: "Mic Mode" })).toBeChecked();
  });

  it("preserves an in-flight voice request and suppresses stale TTS after switching", async () => {
    let releaseResponse;
    const delayedResponse = new Promise((resolve) => {
      releaseResponse = resolve;
    });
    const calls = mockApi({ sendDelay: delayedResponse });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    emitRecognitionResult(voice.recognitions[0], "Keep this submitted request");
    await waitFor(() => {
      expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1);
    });

    await user.click(screen.getByRole("radio", { name: "Message Mode" }));
    releaseResponse();

    expect(await screen.findByText("Keep this submitted request")).toBeInTheDocument();
    expect(await screen.findByText(interim)).toBeInTheDocument();
    expect(calls.filter((call) => call.url === "/api/sessions")).toHaveLength(1);
    expect(voice.synthesis.speak).not.toHaveBeenCalled();
    expect(voice.recognitions).toHaveLength(1);
  });

  it("keeps handoff confirmation and catalog selection available across mode switches", async () => {
    const confirmation =
      "Would you like me to create a queued support ticket for staff to follow up? Please reply yes or no.";
    const calls = mockApi({
      assistantText: [confirmation, "Your response was recorded."],
    });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ mode: "message" });
    await user.type(screen.getByRole("textbox", { name: "Your message" }), "I need a human.");
    await user.keyboard("{Enter}");
    await screen.findByText(confirmation);

    await user.click(screen.getByRole("radio", { name: "Live Call Mode" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    await user.click(screen.getByRole("radio", { name: "Mic Mode" }));
    expect(screen.getByRole("button", { name: "Yes, create ticket" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Yes, create ticket" }));
    expect(await screen.findByText("yes")).toBeInTheDocument();
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Browse Services" }));
    await screen.findByRole("button", { name: /Haircut.*\$35\.00.*30 minutes/ });
    await user.click(screen.getByRole("radio", { name: "Message Mode" }));
    await user.click(screen.getByRole("button", { name: /Haircut.*\$35\.00.*30 minutes/ }));
    expect(await screen.findByText("What is the price and duration of Haircut?")).toBeInTheDocument();
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(3);
    expect(calls.filter((call) => call.url === "/api/sessions")).toHaveLength(1);
  });

  it("loads approved service cards in an accessible panel and closes with focus restored", async () => {
    let resolveServices;
    const servicesResponse = new Promise((resolve) => {
      resolveServices = resolve;
    });
    const calls = mockApi({ serviceDelay: servicesResponse });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /Multimodal Assistant/ }));

    const browseButton = screen.getByRole("button", { name: "Browse Services" });
    await user.click(browseButton);
    expect(screen.getByRole("dialog", { name: "Available services" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading services");

    resolveServices();
    expect(await screen.findByRole("button", { name: /Haircut.*\$35\.00.*30 minutes/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Beard trim.*\$18\.00.*20 minutes/ })).toBeInTheDocument();
    expect(calls.filter((call) => call.url === "/api/services")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Close services" }));
    expect(screen.queryByRole("dialog", { name: "Available services" })).not.toBeInTheDocument();
    expect(browseButton).toHaveFocus();

    await user.click(browseButton);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Available services" })).not.toBeInTheDocument();
    expect(browseButton).toHaveFocus();
  });

  it("shows empty and error states from the catalog API", async () => {
    const user = userEvent.setup();
    mockApi({ servicesList: [] });
    const { unmount } = render(<App />);
    await user.click(await screen.findByRole("button", { name: /Multimodal Assistant/ }));
    await user.click(screen.getByRole("button", { name: "Browse Services" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "No services are currently available.",
    );
    unmount();

    mockApi({ servicesStatus: 503 });
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /Multimodal Assistant/ }));
    await user.click(screen.getByRole("button", { name: "Browse Services" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "server error 503",
    );
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });

  it("submits a selected service through the existing session message API", async () => {
    const calls = mockApi({
      assistantText: "A haircut costs $35 and takes about 30 minutes.",
    });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Browse Services" }));
    const haircutCard = await screen.findByRole("button", {
      name: /Haircut.*\$35\.00.*30 minutes/,
    });
    await user.click(haircutCard);

    expect(await screen.findByText("What is the price and duration of Haircut?")).toBeInTheDocument();
    expect(await screen.findByText("A haircut costs $35 and takes about 30 minutes.")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      session_id: SESSION_ID,
      message_text: "What is the price and duration of Haircut?",
      modality: "text",
    });
    expect(screen.queryByRole("dialog", { name: "Available services" })).not.toBeInTheDocument();
  });

  it("routes a recognized service question through the existing session message API", async () => {
    const calls = mockApi({
      assistantText: "A haircut costs $35 and takes about 30 minutes.",
    });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    emitRecognitionResult(voice.recognitions[0], "How much is a haircut?");

    expect(await screen.findByText("A haircut costs $35 and takes about 30 minutes.")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      session_id: SESSION_ID,
      message_text: "How much is a haircut?",
      modality: "speech_transcript",
    });
  });

  it("disables service-card selection while live recognition is listening", async () => {
    const calls = mockApi();
    mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    await user.click(screen.getByRole("button", { name: "Browse Services" }));

    expect(await screen.findByRole("button", {
      name: /Haircut.*\$35\.00.*30 minutes/,
    })).toBeDisabled();
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
  });

  it("prevents duplicate service-card submissions while the request is pending", async () => {
    let releaseRequest;
    const requestDelay = new Promise((resolve) => {
      releaseRequest = resolve;
    });
    const calls = mockApi({
      sendDelay: requestDelay,
      assistantText: "A grounded response.",
    });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Browse Services" }));
    const haircutCard = await screen.findByRole("button", {
      name: /Haircut.*\$35\.00.*30 minutes/,
    });
    await user.click(haircutCard);
    expect(haircutCard).toBeDisabled();
    releaseRequest();
    await screen.findByText("A grounded response.");
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1);
  });

  it("creates one text_web session, checks its status, and discloses automation", async () => {
    const calls = mockApi();
    render(<App />);

    await waitForReady();

    const createCall = calls.find((call) => call.url === "/api/sessions");
    expect(JSON.parse(createCall.options.body)).toEqual({ channel_type: "text_web" });
    expect(calls.filter((call) => call.url === "/api/sessions")).toHaveLength(1);
    expect(calls.some((call) => call.url === `/api/sessions/${SESSION_ID}`)).toBe(true);
    expect(screen.getByRole("note")).toHaveTextContent(/automated assistant/i);
    expect(screen.getByText(/answers use approved salon information and recorded sample appointment slots/i)).toBeInTheDocument();
  });

  it("sends the normalized text_web contract and renders both messages in sequence", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();

    await user.type(screen.getByRole("textbox", { name: "Your message" }), "What are your hours?");
    await user.keyboard("{Enter}");

    const customer = await screen.findByText("What are your hours?");
    const assistant = await screen.findByText(interim);
    const transcript = screen.getByRole("log", { name: "Conversation" });
    const rendered = within(transcript).getAllByRole("article");
    expect(rendered[1]).toContainElement(customer);
    expect(rendered[2]).toContainElement(assistant);

    const sendCall = calls.find((call) => call.url.endsWith("/messages"));
    const payload = JSON.parse(sendCall.options.body);
    expect(payload).toMatchObject({
      session_id: SESSION_ID,
      channel_type: "text_web",
      modality: "text",
      message_text: "What are your hours?",
    });
    expect(payload.trace_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );
    expect(new Date(payload.timestamp).toISOString()).toBe(payload.timestamp);
    expect(screen.getByText(/automated response generation is not implemented yet/i)).toBeInTheDocument();
    expect(screen.getByText(/typed messages and recognized speech transcripts are stored/i)).toBeInTheDocument();
  });

  it.each([
    [
      "yes",
      "Yes, create ticket",
      "Would you like me to create a queued support ticket for staff to follow up? Please reply yes or no.",
    ],
    [
      "no",
      "No, thanks",
      "Would you like me to create a queued support ticket for staff to follow up? Please reply yes or no.",
    ],
    [
      "yes",
      "Yes, create ticket",
      "I heard both yes and no. Would you like me to create a support ticket?",
    ],
  ])("submits the %s handoff button through the existing message API", async (answer, buttonName, confirmation) => {
    const calls = mockApi({
      assistantText: [confirmation, "Your response has been recorded."],
    });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.type(screen.getByRole("textbox", { name: "Your message" }), "I need a human.");
    await user.keyboard("{Enter}");
    await screen.findByText(confirmation);

    await user.click(screen.getByRole("button", { name: buttonName }));
    await screen.findByText(answer);
    await screen.findByText("Your response has been recorded.");

    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(2);
    expect(JSON.parse(messageCalls[1].options.body).message_text).toBe(answer);
    expect(screen.queryByRole("button", { name: "Yes, create ticket" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "No, thanks" })).not.toBeInTheDocument();
  });

  it("disables handoff buttons while a confirmation response is being submitted", async () => {
    let releaseResponse;
    const delayedResponse = new Promise((resolve) => {
      releaseResponse = resolve;
    });
    const confirmation =
      "Would you like me to create a queued support ticket for staff to follow up? Please reply yes or no.";
    const calls = mockApi({
      assistantText: [confirmation, "Your response has been recorded."],
      sendDelay: [Promise.resolve(), delayedResponse],
    });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.type(screen.getByRole("textbox", { name: "Your message" }), "I need a human.");
    await user.keyboard("{Enter}");
    await screen.findByText(confirmation);

    fireEvent.click(screen.getByRole("button", { name: "Yes, create ticket" }));
    expect(screen.getByRole("button", { name: "Yes, create ticket" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "No, thanks" })).toBeDisabled();
    releaseResponse();
    await screen.findByText("Your response has been recorded.");
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(2);
  });

  it("uses Shift+Enter for a newline and Enter to submit", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();

    const input = screen.getByRole("textbox", { name: "Your message" });
    await user.type(input, "First line");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.type(input, "Second line");

    expect(input).toHaveValue("First line\nSecond line");
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
    await user.keyboard("{Enter}");

    expect(await screen.findByText(/First line\s+Second line/)).toBeInTheDocument();
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1);
  });

  it("shows a sending indicator and prevents rapid duplicate submissions", async () => {
    let releaseSend;
    const sendDelay = new Promise((resolve) => {
      releaseSend = resolve;
    });
    const calls = mockApi({ sendDelay });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();

    const input = screen.getByRole("textbox", { name: "Your message" });
    await user.type(input, "Please help me.");
    fireEvent.submit(input.closest("form"));
    fireEvent.submit(input.closest("form"));

    expect(screen.getByRole("status")).toHaveTextContent("Sending your message");
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1);
    releaseSend();
    await screen.findByText(interim);
  });

  it("keeps the draft and presents safe feedback when the API rejects a turn", async () => {
    mockApi({ sendStatus: 422 });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    const input = screen.getByRole("textbox", { name: "Your message" });
    await user.type(input, "My message");
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That message could not be accepted",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent("internal stack trace");
    expect(input).toHaveValue("My message");
    expect(screen.queryByText("My message", { selector: ".message-bubble" })).not.toBeInTheDocument();
  });

  it("handles an invalid session without continuing to submit turns", async () => {
    mockApi({ sendStatus: 404 });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    const input = screen.getByRole("textbox", { name: "Your message" });
    await user.type(input, "Hello");
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This conversation could not be found",
    );
    expect(screen.getByRole("button", { name: "Start Call" })).toBeEnabled();
    expect(input).toBeDisabled();
  });

  it.each([
    ["complaint flow", "I have a complaint about my visit."],
    ["ambiguous request", "Are you open Saturday and can you book a haircut?"],
  ])("does not claim a ticket or resolve a %s before P13", async (_label, text) => {
    mockApi();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();

    await user.type(screen.getByRole("textbox", { name: "Your message" }), text);
    await user.keyboard("{Enter}");

    expect(await screen.findByText(interim)).toBeInTheDocument();
    expect(screen.queryByText(/ticket (created|filed)|we've resolved/i)).not.toBeInTheDocument();
  });

  it("ends the session safely and allows a fresh session to be started", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();

    await user.click(screen.getByRole("button", { name: "End Call" }));

    expect(await screen.findByText("Conversation ended. Your messages were saved.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Your message" })).toBeDisabled();
    expect(JSON.parse(calls.find((call) => call.url.endsWith("/end")).options.body)).toEqual({
      outcome: "cancelled",
    });
  });

  it("starts a new session after the current one is closed", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "End Call" }));
    await screen.findByText("Conversation ended. Your messages were saved.");
    await user.click(screen.getByRole("button", { name: "Start Call" }));

    await waitFor(() => {
      expect(calls.filter((call) => call.url === "/api/sessions")).toHaveLength(2);
    });
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "Your message" })).toBeEnabled(),
    );
  });

  it("offers a new conversation when the created session is already closed", async () => {
    mockApi({ statusStatus: 409 });
    render(<App />);
    await userEvent.setup().click(await screen.findByRole("button", { name: /Multimodal Assistant/ }));
    await userEvent.setup().click(await screen.findByRole("button", { name: "Start Call" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("conversation has ended");
    expect(screen.getByRole("button", { name: "Start Call" })).toBeEnabled();
  });

  it("starts browser recognition directly without opening a separate microphone stream", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();

    await user.click(screen.getByRole("button", { name: "Start voice input" }));

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    expect(voice.recognitions[0].start).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("Listening");
    expect(screen.getByRole("button", { name: "Cancel voice input" })).toBeInTheDocument();
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
  });

  it("submits a final recognized transcript through the existing chat endpoint", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "Are you open on Wednesday?");

    expect(await screen.findByText("Are you open on Wednesday?")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      session_id: SESSION_ID,
      channel_type: "text_web",
      modality: "speech_transcript",
      message_text: "Are you open on Wednesday?",
    });
    expect(voice.recognitions[0].stop).toHaveBeenCalledOnce();
  });

  it("uses the same existing session for voice and subsequent typed messages", async () => {
    const calls = mockApi({ assistantText: "Wednesday hours are 09:00–18:00 Etc/UTC." });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    emitRecognitionResult(voice.recognitions[0], "Are you open on Wednesday?");
    await screen.findByText("Wednesday hours are 09:00–18:00 Etc/UTC.");

    const input = screen.getByRole("textbox", { name: "Your message" });
    await waitFor(() => expect(input).toBeEnabled());
    await user.type(input, "How much is a haircut?");
    await user.keyboard("{Enter}");
    await screen.findByText("How much is a haircut?");

    const createCalls = calls.filter((call) => call.url === "/api/sessions");
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(createCalls).toHaveLength(1);
    expect(messageCalls).toHaveLength(2);
    expect(messageCalls.map((call) => JSON.parse(call.options.body).session_id)).toEqual([
      SESSION_ID,
      SESSION_ID,
    ]);
  });

  it("speaks the actual backend assistant response, not the recognized transcript", async () => {
    const answer = "We are open Wednesday from 9 AM to 6 PM.";
    mockApi({ assistantText: answer });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    emitRecognitionResult(voice.recognitions[0], "Are you open on Wednesday?");

    expect(await screen.findByText(answer)).toBeInTheDocument();
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    expect(voice.utterances[0].text).toBe(answer);
    expect(voice.utterances[0].text).not.toBe("Are you open Wednesday?");
  });

  it("keeps typed-message responses text-only by default", async () => {
    mockApi({ assistantText: "A grounded typed answer." });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.type(screen.getByRole("textbox", { name: "Your message" }), "Typed question");
    await user.keyboard("{Enter}");

    expect(await screen.findByText("A grounded typed answer.")).toBeInTheDocument();
    expect(voice.synthesis.speak).not.toHaveBeenCalled();
  });

  it("ignores interim results and duplicate final recognition events", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    const recognition = voice.recognitions[0];

    emitRecognitionResult(recognition, "Are you open on Wednesday?", false);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
    emitRecognitionResult(recognition, "Are you open on Wednesday?");
    emitRecognitionResult(recognition, "Are you open on Wednesday?");

    await screen.findByText("Are you open on Wednesday?");
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1);
  });

  it("reports unsupported speech recognition without breaking typed chat", async () => {
    const calls = mockApi();
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: undefined,
    });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Voice input is not supported in this browser",
    );
    const input = screen.getByRole("textbox", { name: "Your message" });
    await user.type(input, "Typed fallback");
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Typed fallback")).toBeInTheDocument();
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1);
  });

  it("handles recognition permission and network errors with their actual categories", async () => {
    const deniedVoice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(deniedVoice.recognitions).toHaveLength(1));
    deniedVoice.recognitions[0].onerror({ error: "not-allowed" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Microphone permission was denied");
    cleanup();

    const networkVoice = mockVoice();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(networkVoice.recognitions).toHaveLength(1));
    networkVoice.recognitions[0].onerror({ error: "network" });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "browser reported a speech-recognition network error",
    );
  });

  it("reports no speech when recognition ends without a final transcript", async () => {
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    voice.recognitions[0].onend();

    expect(await screen.findByRole("alert")).toHaveTextContent("No speech was recognized");
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });

  it("cancels active recognition without submitting a message", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));

    await user.click(screen.getByRole("button", { name: "Cancel voice input" }));

    expect(voice.recognitions[0].abort).toHaveBeenCalledOnce();
    expect(await screen.findByRole("status")).toHaveTextContent("Voice input cancelled");
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
  });

  it("keeps the assistant response readable when speech synthesis is unavailable", async () => {
    const answer = "The assistant response remains available as text.";
    mockApi({ assistantText: answer });
    const voice = mockVoice();
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: undefined,
    });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    emitRecognitionResult(voice.recognitions[0], "Please answer me.");

    expect(await screen.findByText(answer)).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Voice reply is unavailable in this browser",
    );
    expect(voice.synthesis.speak).not.toHaveBeenCalled();
  });

  it("stops playback and cancels overlapping TTS before speaking another voice response", async () => {
    const calls = mockApi({ assistantText: "Assistant answer." });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    emitRecognitionResult(voice.recognitions[0], "First voice question");
    await screen.findByText("Assistant answer.");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    await user.click(screen.getByRole("button", { name: "Stop speech" }));
    expect(voice.synthesis.cancel).toHaveBeenCalled();
    expect(await screen.findByRole("status")).toHaveTextContent("Speech playback stopped");

    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    emitRecognitionResult(voice.recognitions[1], "Second voice question");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledTimes(2));
    expect(voice.synthesis.cancel.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(2);
  });

  it("does not invoke TTS when the voice message request fails", async () => {
    mockApi({ sendStatus: 500 });
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    emitRecognitionResult(voice.recognitions[0], "Are you open Wednesday?");

    expect(await screen.findByRole("alert")).toHaveTextContent("server error 500");
    expect(voice.synthesis.speak).not.toHaveBeenCalled();
    expect(screen.queryByText("Are you open Wednesday?", { selector: ".message-bubble" })).not.toBeInTheDocument();
  });
}); describe("live call mode", () => {
  const user = userEvent.setup();

  it("starts live call mode recognition when selected", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });

    expect(voice.recognitions).toHaveLength(1);
    expect(voice.recognitions[0].start).toHaveBeenCalledOnce();
    expect(calls.filter((call) => call.url === "/api/sessions")).toHaveLength(1);
    expect(JSON.parse(calls.find((call) => call.url === "/api/sessions").options.body))
      .toEqual({ channel_type: "browser_voice" });
    expect(screen.queryByRole("button", { name: "Start voice input" })).not.toBeInTheDocument();
    expect(screen.getByText("Listening", { selector: ".assistant-status" })).toBeInTheDocument();
  });

  it("shows Processing and Speaking in the live-call status", async () => {
    let finishRequest;
    const sendDelay = new Promise((resolve) => {
      finishRequest = resolve;
    });
    mockApi({ sendDelay });
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "Are you open today?");
    await waitFor(() =>
      expect(screen.getByText("Processing", { selector: ".assistant-status" })).toBeInTheDocument(),
    );

    finishRequest();
    await waitFor(() =>
      expect(screen.getByText("Speaking", { selector: ".assistant-status" })).toBeInTheDocument(),
    );
  });

  it("reports a live-call microphone denial from the recognition error", async () => {
    const voice = mockVoice();
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Multimodal Assistant/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Live Call Mode/ }));
    await user.click(screen.getByRole("button", { name: "Start Call" }));
    await screen.findByRole("button", { name: "End Call" });

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    voice.recognitions[0].onerror({ error: "not-allowed" });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Microphone permission was denied",
    );
    expect(screen.getByRole("textbox", { name: "Your message" })).toBeEnabled();
  });

  it("submits a recognized transcript even when browser confidence is low", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "Are you open today?", true, 0.2);

    expect(await screen.findByText("Are you open today?")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body).asr_confidence).toBe(0.2);
  });

  it("submits one final transcript with modality speech_transcript", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "Are you open on Wednesday?", true, 0.91);

    expect(await screen.findByText("Are you open on Wednesday?")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      channel_type: "browser_voice",
      modality: "speech_transcript",
      language: "en-US",
      asr_confidence: 0.91,
    });
    expect(voice.recognitions[0].stop).toHaveBeenCalledOnce();
  });

  it("keeps typed fallback on the browser_voice channel with text modality", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    voice.recognitions[0].onerror({ error: "network" });

    const input = screen.getByRole("textbox", { name: "Your message" });
    await waitFor(() => expect(input).toBeEnabled());
    await user.type(input, "Typed fallback during live call");
    await user.keyboard("{Enter}");
    await screen.findByText("Typed fallback during live call");

    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      channel_type: "browser_voice",
      modality: "text",
      message_text: "Typed fallback during live call",
    });
  });

  it("recognition restarts after TTS completes in live call mode", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "Are you open on Wednesday?");
    await screen.findByText("Are you open on Wednesday?");
    expect(voice.recognitions).toHaveLength(1);
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());

    // Simulate TTS completion by firing onend on the last utterance
    const utterance = voice.utterances[voice.utterances.length - 1];
    if (utterance && typeof utterance.onend === "function") {
      utterance.onend();
    }

    // After TTS completion, recognition should have restarted for live call mode
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
  });

  it("recovers once from no-speech and resumes the normal TTS listening cycle", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    voice.recognitions[0].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    expect(screen.getByText("Listening", { selector: ".assistant-status" })).toBeInTheDocument();

    emitRecognitionResult(voice.recognitions[1], "I want to speak to a human.");
    await screen.findByText("I want to speak to a human.");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    voice.utterances[0].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(3));
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1);
  });

  it.each(["yes", "no"])(
    "restarts after handoff confirmation TTS and submits final %s unchanged once",
    async (answer) => {
      const confirmation =
        "Would you like me to create a queued support ticket for staff to follow up? Please reply yes or no.";
      const calls = mockApi({ assistantText: confirmation });
      const voice = mockVoice();
      render(<App />);
      await waitForReady({ liveCallMode: true });

      await waitFor(() => expect(voice.recognitions).toHaveLength(1));
      emitRecognitionResult(
        voice.recognitions[0],
        "I want to speak to a human.",
      );
      await screen.findByText(confirmation);
      await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());

      voice.utterances[0].onend();
      await waitFor(() => expect(voice.recognitions).toHaveLength(2));
      expect(screen.getByText("Listening", { selector: ".assistant-status" })).toBeInTheDocument();

      emitRecognitionResult(voice.recognitions[1], answer);
      emitRecognitionResult(voice.recognitions[1], answer);
      await screen.findByText(answer, { selector: ".message-bubble" });

      const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
      expect(messageCalls).toHaveLength(2);
      expect(JSON.parse(messageCalls[1].options.body)).toMatchObject({
        channel_type: "browser_voice",
        modality: "speech_transcript",
        message_text: answer,
      });
    },
  );

  it("bounds consecutive no-speech recovery instead of creating a restart loop", async () => {
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    voice.recognitions[0].onerror({ error: "no-speech" });
    voice.recognitions[0].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    voice.recognitions[1].onerror({ error: "no-speech" });
    voice.recognitions[1].onend();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No speech was recognized. Please speak again",
    );
    expect(voice.recognitions).toHaveLength(2);
  });

  it("end call prevents recognition restart from stale callbacks", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "Are you open on Wednesday?");
    await screen.findByText("Are you open on Wednesday?");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());

    // End the call before TTS completes
    await user.click(screen.getByRole("button", { name: "End Call" }));
    expect(voice.synthesis.cancel).toHaveBeenCalled();

    // After ending, TTS should complete without restarting recognition
    const utterance = voice.utterances[voice.utterances.length - 1];
    if (utterance && typeof utterance.onend === "function") {
      utterance.onend();
    }

    // Recognition should NOT have restarted
    expect(voice.recognitions).toHaveLength(1);
  });

  it("automatically listens after Start Call in Live Call Mode", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Multimodal Assistant/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Live Call Mode/ }));

    // Start Call should automatically begin listening
    await user.click(screen.getByRole("button", { name: "Start Call" }));

    // After starting, recognition should be active and listening
    await screen.findByRole("button", { name: "End Call" });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    expect(voice.recognitions).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Listening");
  });

  it("one transcript submitted per recognition cycle in live call mode", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "Are you open on Wednesday?");
    await screen.findByText("Are you open on Wednesday?");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());

    // Only one transcript should be submitted per recognition cycle
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);

    // Submitting another recognition should not create duplicate submissions
    emitRecognitionResult(voice.recognitions[0], "Can I book an appointment?");

    // Should still only have one transcript from the first recognition cycle
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1);
    expect(screen.queryByText("Can I book an appointment?")).not.toBeInTheDocument();
  });

  it("microphone restarts after TTS completion in live call mode", async () => {
    const calls = mockApi();
    const voice = mockVoice({ endUtteranceImmediately: true });
    render(<App />);
    await waitForReady({ liveCallMode: true });

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "Are you open on Wednesday?");
    await screen.findByText("Are you open on Wednesday?");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());

    // TTS ends while the response request is still unwinding; restart waits for it.
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
  });

  it("End Call aborts active recognition without submitting a message", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    await user.click(screen.getByRole("button", { name: "End Call" }));
    expect(voice.recognitions[0].abort).toHaveBeenCalledOnce();

    // Recognition callbacks were detached when the call ended.
    voice.recognitions[0].onresult?.({
      results: [{ 0: { transcript: "stale transcript" }, isFinal: true }],
    });
    expect(voice.recognitions).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
  });

  it("starts a fresh Live Call without stale cancellation state or callbacks", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "First call question.");
    await screen.findByText("First call question.");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    const oldRecognitionResult = voice.recognitions[0].onresult;
    const oldUtteranceEnd = voice.utterances[0].onend;
    const oldUtteranceError = voice.utterances[0].onerror;

    await user.click(screen.getByRole("button", { name: "End Call" }));
    await screen.findByText("Conversation ended. Your messages were saved.");
    await user.click(await screen.findByRole("button", { name: "Start Call" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    expect(screen.getByText("Listening", { selector: ".assistant-status" })).toBeInTheDocument();
    expect(screen.queryByText(/Speech playback stopped because the conversation is ending/)).not.toBeInTheDocument();
    expect(calls.filter((call) => call.url === "/api/sessions")).toHaveLength(2);

    oldRecognitionResult({
      results: [{ 0: { transcript: "stale confirmation" }, isFinal: true }],
    });
    oldUtteranceEnd();
    oldUtteranceError({ error: "canceled" });
    expect(voice.recognitions).toHaveLength(2);
    expect(screen.getByText("Listening", { selector: ".assistant-status" })).toBeInTheDocument();

    emitRecognitionResult(voice.recognitions[1], "Second call question.");
    await screen.findByText("Second call question.");
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(2);
    expect(messageCalls[1].url).not.toBe(messageCalls[0].url);
    expect(JSON.parse(messageCalls[1].options.body).session_id).not.toBe(
      JSON.parse(messageCalls[0].options.body).session_id,
    );
  });

  it("keeps End Call available during a speech request and suppresses stale TTS", async () => {
    let releaseSend;
    const calls = mockApi({
      sendDelay: new Promise((resolve) => {
        releaseSend = resolve;
      }),
    });
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });

    emitRecognitionResult(voice.recognitions[0], "A question while the request is pending.");
    await waitFor(() =>
      expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(1),
    );
    expect(screen.getByRole("button", { name: "End Call" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "End Call" }));
    expect(voice.synthesis.cancel).toHaveBeenCalled();
    expect(await screen.findByText("Conversation ended. Your messages were saved.")).toBeInTheDocument();

    releaseSend();
    await screen.findByText("A question while the request is pending.");
    await waitFor(() => expect(calls.filter((call) =>
      call.url === `/api/sessions/${SESSION_ID}`,
    )).toHaveLength(2));
    expect(voice.synthesis.speak).not.toHaveBeenCalled();
    expect(voice.recognitions).toHaveLength(1);
  });

  it("safe behavior when TTS fails or is unavailable in live call mode", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "Are you open on Wednesday?");
    await screen.findByText("Are you open on Wednesday?");
    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());

    // Simulate TTS failure by firing onerror
    const utterance = voice.utterances[voice.utterances.length - 1];
    if (utterance && utterance.onerror) {
      utterance.onerror({ error: "failed" });
    }

    // Should not crash or enter infinite loop
    expect(voice.recognitions.length).toBeLessThanOrEqual(2);
  });

  it("handles recognition errors safely without uncontrolled restart", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Multimodal Assistant/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Live Call Mode/ }));

    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: voice.SpeechRecognition,
    });

    await user.click(screen.getByRole("button", { name: "Start Call" }));
    await screen.findByRole("button", { name: "End Call" });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    const recognition = voice.recognitions[0];
    recognition.onerror({ error: "network" });
    recognition.onend();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "browser reported a speech-recognition network error",
    );
    expect(voice.recognitions).toHaveLength(1);
  });
});

describe("UX06 English voice recognition reliability", () => {
  const user = userEvent.setup();

  it("submits isolated short word 'yes' when delivered as final result in Mic Mode", async () => {
    const calls = mockApi({ assistantText: "Your response was recorded." });
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "yes", true, 0.95);

    expect(await screen.findByText("yes")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      session_id: SESSION_ID,
      channel_type: "text_web",
      modality: "speech_transcript",
      message_text: "yes",
      asr_confidence: 0.95,
    });
  });

  it("submits isolated short word 'no' when delivered as final result in Live Call Mode", async () => {
    const calls = mockApi({ assistantText: "Understood." });
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "no", true, 0.88);

    expect(await screen.findByText("no")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      channel_type: "browser_voice",
      modality: "speech_transcript",
      message_text: "no",
      asr_confidence: 0.88,
    });
  });

  it("submits isolated short word 'okay' when delivered as final result in Call-Only Mode", async () => {
    const calls = mockApi({ assistantText: "Acknowledged." });
    const voice = mockVoice();
    render(<App />);
    await waitForCallOnlyReady();
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "okay", true, 0.92);

    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      channel_type: "browser_voice",
      modality: "speech_transcript",
      message_text: "okay",
      asr_confidence: 0.92,
    });
  });

  it("rescues interim short word 'yes' on onend when browser fails to emit isFinal in Mic Mode", async () => {
    const calls = mockApi({ assistantText: "Your confirmation was processed." });
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    // Browser emits interim result only, then closes
    emitRecognitionResult(voice.recognitions[0], "yes", false, 0.85);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);

    voice.recognitions[0].onend();

    expect(await screen.findByText("yes")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      modality: "speech_transcript",
      message_text: "yes",
    });
  });

  it("rescues interim short word 'no' on onend when browser fails to emit isFinal in Live Call Mode", async () => {
    const calls = mockApi({ assistantText: "Understood, cancelled." });
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "no", false, 0.81);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);

    voice.recognitions[0].onend();

    expect(await screen.findByText("no")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      channel_type: "browser_voice",
      message_text: "no",
    });
  });

  it("rescues interim short word 'ok' on onend even when browser emits no-speech error before closing", async () => {
    const calls = mockApi({ assistantText: "Great, moving forward." });
    const voice = mockVoice();
    render(<App />);
    await waitForCallOnlyReady();
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    // Chrome sends interim "ok", then times out with no-speech and onend
    emitRecognitionResult(voice.recognitions[0], "ok", false, 0.79);
    voice.recognitions[0].onerror?.({ error: "no-speech" });
    voice.recognitions[0].onend();

    await waitFor(() => expect(voice.synthesis.speak).toHaveBeenCalledOnce());
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
    expect(JSON.parse(messageCalls[0].options.body)).toMatchObject({
      message_text: "ok",
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("prevents duplicate submissions when interim result is followed by final result", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    // Interim followed by final
    emitRecognitionResult(voice.recognitions[0], "yes", false);
    emitRecognitionResult(voice.recognitions[0], "yes", true);
    voice.recognitions[0].onend();

    expect(await screen.findByText("yes")).toBeInTheDocument();
    const messageCalls = calls.filter((call) => call.url.endsWith("/messages"));
    expect(messageCalls).toHaveLength(1);
  });

  it("discards interim transcript if voice input was cancelled before onend", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    emitRecognitionResult(voice.recognitions[0], "yes", false);
    await user.click(screen.getByRole("button", { name: "Cancel voice input" }));

    voice.recognitions[0].onend();

    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
    expect(screen.queryByText("yes", { selector: ".message-bubble" })).not.toBeInTheDocument();
  });

  it("ignores stale onresult and onend callbacks after mode switch away from Mic", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    const micRec = voice.recognitions[0];

    await user.click(screen.getByRole("radio", { name: "Message Mode" }));

    micRec.onresult?.({
      results: [{ 0: { transcript: "stale yes" }, isFinal: false }],
    });
    micRec.onend?.();

    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
  });

  it("genuine silence in Mic Mode does not submit and displays prompt to retry or type", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ mode: "mic" });
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    voice.recognitions[0].onerror?.({ error: "no-speech" });
    voice.recognitions[0].onend();

    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No speech was recognized. Please try again or type your message.",
    );
  });

  it("genuine silence in Live Call Mode performs bounded recovery without infinite loop", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    render(<App />);
    await waitForReady({ liveCallMode: true });
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

    voice.recognitions[0].onerror?.({ error: "no-speech" });
    voice.recognitions[0].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(2));
    expect(screen.getByText("Listening", { selector: ".assistant-status" })).toBeInTheDocument();

    voice.recognitions[1].onerror?.({ error: "no-speech" });
    voice.recognitions[1].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(3));

    voice.recognitions[2].onerror?.({ error: "no-speech" });
    voice.recognitions[2].onend();
    await waitFor(() => expect(voice.recognitions).toHaveLength(4));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No speech was recognized. Please speak again or type your message.",
    );
    expect(voice.recognitions).toHaveLength(4);
    expect(calls.filter((call) => call.url.endsWith("/messages"))).toHaveLength(0);
  });
});
