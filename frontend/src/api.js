const API_ROOT = "/api";

export class ApiError extends Error {
  constructor(status) {
    super(`Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(0);
  }

  if (!response.ok) {
    throw new ApiError(response.status);
  }

  return response.json();
}

export function createSession() {
  return request("/sessions", {
    method: "POST",
    body: JSON.stringify({ channel_type: "text_web" }),
  });
}

export function getSessionStatus(sessionId) {
  return request(`/sessions/${encodeURIComponent(sessionId)}`);
}

export function sendMessage({ sessionId, text }) {
  return request(`/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      trace_id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      channel_type: "text_web",
      modality: "text",
      message_text: text,
    }),
  });
}

export function endSession(sessionId) {
  return request(`/sessions/${encodeURIComponent(sessionId)}/end`, {
    method: "POST",
    body: JSON.stringify({ outcome: "cancelled" }),
  });
}

export function safeErrorMessage(error, action) {
  if (!(error instanceof ApiError)) {
    return `We couldn't ${action}. Please try again.`;
  }
  if (error.status === 0) {
    return "We couldn't reach the service. Check that the backend is running, then try again.";
  }
  if (error.status === 404) {
    return "This conversation could not be found. Start a new conversation to continue.";
  }
  if (error.status === 409) {
    return "This conversation has ended. Start a new conversation to continue.";
  }
  if (error.status === 422) {
    return "That message could not be accepted. Edit it and try again.";
  }
  return `We couldn't ${action} (server error ${error.status}). Please try again.`;
}
