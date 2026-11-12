import { useState } from "react";

/**
 * How TECHOHUB works — static architecture / workflow page.
 *
 * Source of truth: docs/03_SYSTEM_ARCHITECTURE.md, docs/04_LANGGRAPH_ROUTING_AND_AGENTS.md,
 * docs/05_BUSINESS_CAPABILITIES_CRM_BOOKING_TICKETS_MCP.md, docs/06_CHANNELS_SPEECH_AND_TELEPHONY.md,
 * docs/07_KNOWLEDGE_OKF_RETRIEVAL_AND_RAG.md and docs/diagrams/01_END_TO_END_REQUEST_FLOW.dot.
 *
 * Colors follow the diagram legend:
 *   blue   = core / stable application node
 *   green  = baseline local provider or required safe evidence source
 *   amber  = future / conditional / not claimed implemented
 *   red    = risk gate, clarification, permission or human escalation
 */

function Arrow({ fromRight = true }) {
  return (
    <svg
      className="arch-flow-arrow"
      viewBox="0 0 26 10"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <marker
          id="arch-arrow-head"
          markerWidth="8"
          markerHeight="8"
          refX="7"
          refY="4"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L8,4 L0,8 Z" fill="#465670" />
        </marker>
      </defs>
      <line
        x1="2"
        y1="5"
        x2={fromRight ? 24 : 2}
        y2="5"
        stroke="#465670"
        strokeWidth="2"
        markerEnd="url(#arch-arrow-head)"
      />
    </svg>
  );
}

function Card({ title, body, variant = "core", note }) {
  const accent = {
    core: { bg: "#eff6ff", border: "#bfd7ee", dot: "#2563eb" },
    local: { bg: "#f0fdf4", border: "#bbf7d0", dot: "#15803d" },
    future: { bg: "#fffbeb", border: "#fddebd", dot: "#d97706" },
    risk: { bg: "#fef2f2", border: "#fecaca", dot: "#b91c1c" },
  }[variant];

  return (
    <article className="arch-card" style={{ borderColor: accent.border }}>
      <div className="arch-card-head">
        <span
          className="arch-card-dot"
          style={{ backgroundColor: accent.dot }}
          aria-hidden="true"
        />
        <span className="arch-card-title">{title}</span>
      </div>
      <div className="arch-card-body">{body}</div>
      {note && (
        <p className="arch-card-note">{note}</p>
      )}
    </article>
  );
}

export default function ArchitecturePage({ onBack }) {
  const [view, setView] = useState("flow");

  return (
    <main className="arch-page" role="document" aria-label="TECHOHUB system workflow">
      <header className="arch-header">
        <button
          className="arch-back"
          type="button"
          onClick={onBack}
          aria-label="Return to assistant"
        >
          <span aria-hidden="true">←</span> Back to assistant
        </button>
        <div className="arch-brand">
          <span className="arch-wordmark-mark" aria-hidden="true">
            T
          </span>
          <span>
            TECHOHUB<span className="arch-wordmark-period">.</span>
          </span>
        </div>
        <div className="arch-header-copy">
          <h1>How TECHOHUB works</h1>
          <p className="arch-lead">
            A static walkthrough of the customer request pipeline — from your
            message to a grounded assistant reply.
          </p>
        </div>
      </header>

      <nav className="arch-tabs" aria-label="Workflow sections">
        <button
          className={`arch-tab ${view === "flow" ? "arch-tab-active" : ""}`}
          type="button"
          onClick={() => setView("flow")}
        >
          01 · End-to-end flow
        </button>
        <button
          className={`arch-tab ${view === "entry" ? "arch-tab-active" : ""}`}
          type="button"
          onClick={() => setView("entry")}
        >
          02 · Customer entry
        </button>
        <button
          className={`arch-tab ${view === "routing" ? "arch-tab-active" : ""}`}
          type="button"
          onClick={() => setView("routing")}
        >
          03 · Intent & routing
        </button>
        <button
          className={`arch-tab ${view === "paths" ? "arch-tab-active" : ""}`}
          type="button"
          onClick={() => setView("paths")}
        >
          04 · Simple vs complex path
        </button>
        <button
          className={`arch-tab ${view === "knowledge" ? "arch-tab-active" : ""}`}
          type="button"
          onClick={() => setView("knowledge")}
        >
          05 · Knowledge & RAG
        </button>
        <button
          className={`arch-tab ${view === "mcp" ? "arch-tab-active" : ""}`}
          type="button"
          onClick={() => setView("mcp")}
        >
          06 · MCP
        </button>
        <button
          className={`arch-tab ${view === "output" ? "arch-tab-active" : ""}`}
          type="button"
          onClick={() => setView("output")}
        >
          07 · Response & output
        </button>
        <button
          className={`arch-tab ${view === "safety" ? "arch-tab-active" : ""}`}
          type="button"
          onClick={() => setView("safety")}
        >
          08 · Safety & constraints
        </button>
      </nav>

      {view === "flow" && (
        <section className="arch-section">
          <h2 className="arch-section-title">
            <span className="arch-num">01</span> End-to-end request flow
          </h2>
          <div className="arch-flow">
            <div className="arch-flow-node arch-node-customer">
              Customer
              <span className="arch-sub">Text · Browser mic · Future phone</span>
            </div>
            <Arrow />
            <div className="arch-flow-node arch-node-channel">
              Channel adapter
              <span className="arch-sub">
                Session, call events, transport
              </span>
            </div>
            <Arrow />
            <div className="arch-flow-node arch-node-voice variant-future">
              STT provider
              <span className="arch-sub">Audio → utterance text</span>
            </div>
            <Arrow />
            <div className="arch-flow-node arch-node-unified">
              Unified text request
              <span className="arch-sub">
                text + session + channel + metadata
              </span>
            </div>
            <Arrow />
            <div className="arch-flow-node arch-node-guard">
              Precheck
              <span className="arch-sub">Disclosure · consent · risk</span>
            </div>
            <Arrow />
            <div className="arch-flow-node arch-node-route">
              Intent / complexity / risk
              <span className="arch-sub">routing decision</span>
            </div>
          </div>
          <p className="arch-flow-note">
            Voice input is transcribed to text before it reaches the assistant
            core; typed input skips STT. The same session is reused across turns.
          </p>
        </section>
      )}

      {view === "entry" && (
        <section className="arch-section">
          <h2 className="arch-section-title">
            <span className="arch-num">02</span> Customer entry
          </h2>
          <p className="arch-section-lead">
            The customer can start in any supported experience. Each uses the
            same assistant and approved salon information.
          </p>
          <div className="arch-grid">
            <Card
              title="Message Mode"
              body="Typed chat in the browser. Text input only; no microphone required."
              variant="core"
            />
            <Card
              title="Mic Mode"
              body="Press the mic button to speak; the final transcript is submitted as a text message."
              variant="local"
            />
            <Card
              title="Live Call Mode"
              body="Continuous speech-first turn-taking with automatic no-speech recovery and bounded retries."
              variant="local"
            />
            <Card
              title="Call-Only"
              body="Speech-first browser conversation with spoken replies (TTS). Not a telephone call."
              variant="local"
            />
            <Card
              title="Browse Services"
              body="Open the approved service catalog to see price and duration for each service."
              variant="core"
            />
            <Card
              title="Input type"
              body="Text or voice. Voice is normalized to text before routing; a typed fallback is always available."
              variant="core"
            />
          </div>
        </section>
      )}

      {view === "routing" && (
        <section className="arch-section">
          <h2 className="arch-section-title">
            <span className="arch-num">03</span> Intent & routing
          </h2>
          <p className="arch-section-lead">
            Every normalized request passes through the LangGraph router, which
            classifies intent and complexity before dispatching.
          </p>
          <div className="arch-grid">
            <Card
              title="Intent classification"
              body="Rules-first deterministic classifier; Groq model used only when a safe local classification cannot be established. Output is validated locally — it never answers or acts on its own."
              variant="core"
            />
            <Card
              title="Complexity / risk"
              body="Simple requests take the deterministic path; complex or multi-step requests route to a specialized agent subgraph. Unsafe or unknown requests clarify or escalate to a human."
              variant="risk"
            />
            <Card
              title="Simple path"
              body="FAQ, business hours, service catalog, read-only availability — answered directly from approved knowledge or fixture data."
              variant="local"
            />
            <Card
              title="Complex path"
              body="Specialized reasoning agent receives only the tools, context and authority needed for its task. Final writes remain guarded deterministic services."
              variant="core"
            />
            <Card
              title="Clarify / escalate"
              body="Ambiguous, unsupported or policy-sensitive requests ask for clarification or hand off to a human queue — never fabricate an answer."
              variant="risk"
            />
            <Card
              title="Multi-intent"
              body="Clearly multi-request messages are split into supported sub-requests or clarified; shared state is preserved across the turn."
              variant="core"
            />
          </div>
        </section>
      )}

      {view === "paths" && (
        <section className="arch-section">
          <h2 className="arch-section-title">
            <span className="arch-num">04</span> Simple vs complex path
          </h2>
          <p className="arch-section-lead">
            Two downstream branches after routing, rejoining at safety
            verification before the response is returned.
          </p>
          <div className="arch-branches">
            <div className="arch-branch arch-branch-simple">
              <div className="arch-branch-head">
                <span className="arch-branch-dot local" aria-hidden="true" />
                Simple / deterministic
              </div>
              <div className="arch-branch-body">
                <ul>
                  <li>
                    FAQ / service policy answered from <strong>approved OKF
                      knowledge</strong>
                  </li>
                  <li>
                    Business hours and catalog price/duration from the
                    <strong>demo salon fixture</strong>
                  </li>
                  <li>
                    Read-only availability from recorded fixture slots (not a
                    live calendar)
                  </li>
                  <li>
                    Direct grounded answer with source IDs and retrieval reason
                  </li>
                </ul>
              </div>
            </div>
            <div className="arch-branch arch-branch-complex">
              <div className="arch-branch-head">
                <span className="arch-branch-dot core" aria-hidden="true" />
                Complex / agent
              </div>
              <div className="arch-branch-body">
                <ul>
                  <li>
                    Specialized agent subgraph for multi-step complaints,
                    negotiations or multi-intent requests
                  </li>
                  <li>
                    Agent receives only the tools, context and authority it
                    needs
                  </li>
                  <li>
                    Final booking/ticket writes remain guarded deterministic
                    services
                  </li>
                  <li>
                    Explicit user confirmation required before any consequential
                    action
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <div className="arch-flow-note">
            Both paths converge at response verification: evidence, access,
            explicit confirmation and idempotency are checked before anything is
            returned or committed.
          </div>
        </section>
      )}

      {view === "knowledge" && (
        <section className="arch-section">
          <h2 className="arch-section-title">
            <span className="arch-num">05</span> Knowledge & RAG
          </h2>
          <p className="arch-section-lead">
            Answers are grounded in approved sources, not invented.
          </p>
          <div className="arch-grid">
            <Card
              title="OKF knowledge bundle"
              body="Open Knowledge Format — Git-friendly Markdown with YAML frontmatter and an index.md entry point. Only index-linked, frontmatter-marked approved records are eligible."
              variant="local"
            />
            <Card
              title="Retrieval"
              body="OKF-first lexical/semantic retrieval. Evidence excerpts carry stable document IDs and versions; exact rule matching does not invent a confidence score."
              variant="local"
            />
            <Card
              title="Fixture precedence"
              body="Operating hours and catalog services come from the approved demo salon fixture. Schedule status comes from the booking provider; customer records from CRM — never from static policy files."
              variant="local"
            />
            <Card
              title="Abstention"
              body="Unsupported or ambiguous queries are answered with a safe clarification or abstention — never a fabricated price, policy or approval."
              variant="risk"
            />
          </div>
        </section>
      )}

      {view === "mcp" && (
        <section className="arch-section">
          <h2 className="arch-section-title">
            <span className="arch-num">06</span> MCP
          </h2>
          <p className="arch-section-lead">
            Model Context Protocol provides scoped, reusable tool surfaces — used
            selectively, never as the only path.
          </p>
          <div className="arch-grid">
            <Card
              title="MCP client / server"
              body="The MCP client connects to an MCP server exposing approved CRM, booking and ticket tools. Native direct service calls remain available and are preferred for local deterministic lookups."
              variant="core"
            />
            <Card
              title="Approved tools only"
              body="Allowlisted, schema-checked tools (e.g. customer lookup, availability check, ticket creation). Tool execution receives verified server-side auth context — never raw customer IDs from the model."
              variant="core"
            />
            <Card
              title="Selective use"
              body="MCP is an alternative integration surface, not an intrinsic requirement. Adding a remote hop for every local lookup adds latency; local domain services are reused where possible."
              variant="future"
            />
            <Card
              title="Safety"
              body="MCP exposure and tool descriptions are guarded against injection; external providers are optional and not committed for the baseline demo."
              variant="risk"
            />
          </div>
        </section>
      )}

      {view === "output" && (
        <section className="arch-section">
          <h2 className="arch-section-title">
            <span className="arch-num">07</span> Response & output
          </h2>
          <p className="arch-section-lead">
            The verified, grounded response flows back to the customer.
          </p>
          <div className="arch-flow">
            <div className="arch-flow-node arch-node-response">
              Grounded response
              <span className="arch-sub">text + source IDs + outcome</span>
            </div>
            <Arrow />
            <div className="arch-flow-node arch-node-output variant-local">
              Text reply
              <span className="arch-sub">shown in the transcript</span>
            </div>
            <Arrow variant="future" />
            <div className="arch-flow-node arch-node-tts variant-future">
              TTS provider
              <span className="arch-sub">text → spoken output (voice modes)</span>
            </div>
          </div>
          <div className="arch-grid">
            <Card
              title="Grounded answer"
              body="Cites approved sources with version/ID. Unsupported answers abstain or clarify rather than invent policy."
              variant="local"
            />
            <Card
              title="Text or spoken"
              body="Typed replies remain text-only by default. Voice and Call-Only modes speak the assistant response via browser speech synthesis after a successful voice turn."
              variant="local"
            />
            <Card
              title="Audit log"
              body="Every turn and outcome is recorded independently of agent discretion, with correlation IDs for traceability."
              variant="core"
            />
          </div>
        </section>
      )}

      {view === "safety" && (
        <section className="arch-section">
          <h2 className="arch-section-title">
            <span className="arch-num">08</span> Safety & constraints
          </h2>
          <p className="arch-section-lead">
            Guardrails that keep the demo honest and safe.
          </p>
          <div className="arch-grid">
            <Card
              title="Demo mode"
              body="Academic prototype. Approved salon information and recorded sample slots only — no real bookings, CRM access, or staff transfer."
              variant="risk"
            />
            <Card
              title="Synthetic availability"
              body="Appointment slots are recorded fixture data, explicitly labeled as such — never presented as live calendar availability."
              variant="risk"
            />
            <Card
              title="Safe support handoff"
              body="A queued support ticket is created only on explicit customer confirmation (yes/no). No tickets are created from silence or acknowledgements."
              variant="risk"
            />
            <Card
              title="No secret disclosure"
              body="API keys, credentials, environment variables and system prompts are never shared or echoed in customer replies."
              variant="risk"
            />
            <Card
              title="Typed fallback"
              body="Microphone denial or poor STT confidence immediately offers typed input — the conversation never becomes stuck on voice."
              variant="local"
            />
          </div>
        </section>
      )}

      <footer className="arch-footer">
        <p>
          TECHOHUB · Academic prototype ·{" "}
          <a href="/" rel="noopener noreferrer" target="_blank">
            View architecture docs
          </a>
        </p>
        <button className="arch-back" type="button" onClick={onBack}>
          <span aria-hidden="true">←</span> Return to assistant
        </button>
      </footer>
    </main>
  );
}
