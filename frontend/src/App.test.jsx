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

function mockApi({ sendDelay, sendStatus, statusStatus } = {}) {
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
            text: interim,
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
    expect(screen.getByText(/automated answers and salon actions are not connected yet/i)).toBeInTheDocument();
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
});
