export const API_ROOT = (import.meta.env.VITE_API_BASE_URL || "/api").replace(
  /\/+$/,
  "");

export class ApiError extends Error {
  constructor(status) {
    super(`Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

function sessionHeaders(accessToken) {
  const headers = {};
  if (accessToken) {
    headers["X-Session-Token"] = accessToken;
  }
  return headers;
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

export function createSession(channelType = "text_web") {
  return request("/sessions", {
    method: "POST",
    body: JSON.stringify({ channel_type: channelType }),
  });
}

export function getServices() {
  return request("/services");
}

export function getSessionStatus(sessionId, accessToken) {
  return request(`/sessions/${encodeURIComponent(sessionId)}`, {
    headers: sessionHeaders(accessToken),
  });
}

export function sendMessage({
  sessionId,
  channelType = "text_web",
  text,
  modality = "text",
  language,
  asrConfidence,
  accessToken,
}) {
  return request(`/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    headers: sessionHeaders(accessToken),
    body: JSON.stringify({
      session_id: sessionId,
      trace_id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      channel_type: channelType,
      modality,
      message_text: text,
      ...(language ? { language } : {}),
      ...(asrConfidence !== undefined ? { asr_confidence: asrConfidence } : {}),
    }),
  });
}

export function endSession(sessionId, accessToken) {
  return request(`/sessions/${encodeURIComponent(sessionId)}/end`, {
    method: "POST",
    headers: sessionHeaders(accessToken),
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
  if (error.status === 401) {
    return "This conversation session is no longer valid. Start a new conversation.";
  }
  if (error.status === 422) {
    return "That message could not be accepted. Edit it and try again.";
  }
  return `We couldn't ${action} (server error ${error.status}). Please try again.`;
}
