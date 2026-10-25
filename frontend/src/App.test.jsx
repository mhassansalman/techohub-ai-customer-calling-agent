import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App.jsx";

const SESSION_ID = "1608b129-9ab8-46f7-9dd7-6fb2a4b216fc";
const disclosure = "I am an automated assistant. This demo stores text messages.";
const interim =
  "Your message was recorded. Automated response generation is not implemented yet.";

function sessionPayload(status = "active") {
  return {
    session_id: SESSION_ID,
    channel_type: "text_web",
    status,
    started_at: "2026-10-25T08:00:00Z",
    ended_at: null,
    outcome: null,
    message_count: 1,
    audit_event_count: 1,
  };
}

function messagePayload({ id, role, sequence, text }) {
  return {
    message_id: id,
    session_id: SESSION_ID,
    sequence,
    role,
    text,
    timestamp: "2026-10-25T08:01:00Z",
    modality: role === "assistant" ? "text" : "text",
  };
}

function mockApi({ sendDelay, sendStatus, statusStatus, assistantText = interim } = {}) {
  const calls = [];
  let messageNumber = 0;
  globalThis.fetch = vi.fn(async (url, options = {}) => {
    calls.push({ url, options });
    if (url === "/api/sessions" && options.method === "POST") {
      return new Response(
        JSON.stringify({
          session: sessionPayload(),
          assistant_disclosure: disclosure,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url === `/api/sessions/${SESSION_ID}` && !options.method) {
      if (statusStatus) {
        return new Response(JSON.stringify({ detail: "private backend detail" }), {
          status: statusStatus,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(sessionPayload()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url === `/api/sessions/${SESSION_ID}/messages`) {
      if (sendDelay) await sendDelay;
      if (sendStatus) {
        return new Response(JSON.stringify({ detail: "internal stack trace" }), {
          status: sendStatus,
          headers: { "Content-Type": "application/json" },
        });
      }
      messageNumber += 1;
      const payload = JSON.parse(options.body);
      return new Response(
        JSON.stringify({
          customer_message: messagePayload({
            id: `customer-${messageNumber}`,
            role: "customer",
            sequence: messageNumber * 2,
            text: payload.message_text,
          }),
          assistant_message: messagePayload({
            id: `assistant-${messageNumber}`,
            role: "assistant",
            sequence: messageNumber * 2 + 1,
            text: assistantText,
          }),
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url === `/api/sessions/${SESSION_ID}/end`) {
      return new Response(JSON.stringify(sessionPayload("closed")), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected API request: ${options.method} ${url}`);
  });
  return calls;
}

function mockVoice({ microphoneError } = {}) {
  const recognitions = [];
  const utterances = [];
  const tracks = [{ stop: vi.fn() }];

  class MockSpeechRecognition {
    start = vi.fn();
    stop = vi.fn(() => this.onend?.());
    abort = vi.fn(() => this.onend?.());

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

  const getUserMedia = vi.fn(async () => {
    if (microphoneError) throw microphoneError;
    return { getTracks: () => tracks };
  });
  const synthesis = {
    cancel: vi.fn(),
    speak: vi.fn((utterance) => utterance.onstart?.()),
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
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia },
  });

  return { recognitions, utterances, getUserMedia, synthesis, tracks };
}

function emitRecognitionResult(recognition, transcript, isFinal = true) {
  recognition.onresult({
    results: [{ 0: { transcript }, isFinal }],
  });
}

async function waitForReady() {
  await screen.findByText(disclosure);
  await screen.findByRole("textbox", { name: "Your message" });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("browser text chat", () => {
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
    expect(screen.getByRole("button", { name: "Start a new conversation" })).toBeEnabled();
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

    await user.click(screen.getByRole("button", { name: "End chat" }));

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
    await user.click(screen.getByRole("button", { name: "End chat" }));
    await screen.findByText("Conversation ended. Your messages were saved.");
    await user.click(screen.getByRole("button", { name: "Start a new conversation" }));

    await waitFor(() => {
      expect(calls.filter((call) => call.url === "/api/sessions")).toHaveLength(2);
    });
    expect(screen.getByRole("textbox", { name: "Your message" })).toBeEnabled();
  });

  it("offers a new conversation when the created session is already closed", async () => {
    mockApi({ statusStatus: 409 });
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("conversation has ended");
    expect(screen.getByRole("button", { name: "Start a new conversation" })).toBeEnabled();
  });

  it("starts browser recognition and requests microphone permission", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();

    await user.click(screen.getByRole("button", { name: "Start voice input" }));

    await waitFor(() => expect(voice.recognitions).toHaveLength(1));
    expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(voice.tracks[0].stop).toHaveBeenCalledOnce();
    expect(voice.recognitions[0].start).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("Listening");
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
      modality: "text",
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
    expect(voice.utterances[0].text).not.toBe("Are you open on Wednesday?");
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

  it("handles denied microphone permission and recognition network errors", async () => {
    const deniedVoice = mockVoice({ microphoneError: new DOMException("denied", "NotAllowedError") });
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Microphone permission was denied");
    expect(deniedVoice.recognitions).toHaveLength(0);
    cleanup();

    const networkVoice = mockVoice();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(networkVoice.recognitions).toHaveLength(1));
    networkVoice.recognitions[0].onerror({ error: "network" });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Speech recognition could not reach its service",
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

    expect(await screen.findByRole("status")).toHaveTextContent("No speech was recognized");
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });

  it("cancels active recognition without submitting a message", async () => {
    const calls = mockApi();
    const voice = mockVoice();
    const user = userEvent.setup();
    render(<App />);
    await waitForReady();
    await user.click(screen.getByRole("button", { name: "Start voice input" }));
    await waitFor(() => expect(voice.recognitions).toHaveLength(1));

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
});
