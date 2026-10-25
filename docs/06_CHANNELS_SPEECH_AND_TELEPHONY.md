# 06 — Channels, STT/TTS and Telephony

## Final decision: normalize BEFORE the AI core

**Correct boundary:**

`Customer audio -> Channel adapter / transport+session -> Speech-to-text -> Unified text request -> LangGraph -> Unified text response -> Text directly OR TTS -> original channel.`

For typed input, skip STT. Do not put STT before the low-level channel adapter: call signaling, microphone permissions, audio codec and session lifecycle have to be handled by it. Likewise, we should not convert *a whole phone call* after it ends; real-time/turn-based STT processes incoming chunks/utterances.

## Communication channels

| Channel | Input/output | Baseline/future | Issues |
|---|---|---|---|
| Text Web UI | text/text | Baseline required fallback | Session state, authentication |
| Browser Voice | browser mic audio / browser/local TTS | Baseline voice demo | Browser permission, mic quality, STT latency |
| Mock Call | simulated call events / text or mocked audio | Useful baseline tester | Realistic disconnect, retry, transcript flow |
| Twilio | telephony media / streamed voice | Optional later | Number availability, usage charges, webhooks, media streams |
| SIP/VoIP | SIP/RTP | Optional later | Server setup, signaling/audio streaming and codecs |
| Personal SIM / GSM | cellular audio through device/gateway | Experimental only | Android call-audio restrictions, device/hardware and carrier issues |

The assignment explicitly allows a browser/simulated call; don't let paid telephony block mandatory functionality.

## Two abstractions (avoid wrong abstraction)

- `ChannelAdapter`: accepts inbound events (start/text/audio/end/interrupt), attaches correlation/channel IDs, provides backpressure and outbound transport.
- `AudioTransport` / `SpeechPipeline`: exchanges audio frames and handles STT/TTS/VAD where needed.

**Canonical text request:** `session_id, timestamp, channel_type, message_text, language, asr_confidence?, customer_context?, trace_id`.

Keep optional raw audio references out of LangGraph state unless specifically needed, consented and secured.

## Voice providers

| Port | Local/browser examples | Cloud examples | Decision |
|---|---|---|---|
| `STTProvider` | faster-whisper, browser speech recognition (browser-dependent) | Deepgram, OpenAI transcription | Port mandatory; local/browser first |
| `TTSProvider` | Piper, browser speech synthesis | ElevenLabs, OpenAI speech | Port mandatory; local/browser first |
| `VADProvider` | Silero VAD | Managed voice activity services | Optional to improve streaming turns |
| `LLMProvider` | Ollama if hardware permits | Provider APIs | Swappable; fallback needed |

Browser speech APIs are not universally available, offline or consistent; always provide typed fallback. Local TTS/STT runtime performance and language quality must be benchmarked rather than assumed.

## Streaming upgrade path

**Phase 1:** Record/stream one utterance, transcribe, get answer, synthesize playback. This supports the graded demo and is debuggable.  
**Phase 2:** Incremental STT, endpoint detection, partial transcript, streaming response, interruption/barge-in and cancellation of in-flight TTS.  
**Phase 3:** Telephone media stream with SIP/Twilio provider-specific resampling, session events and reconnect strategy.

At all phases LangGraph still sees text turns plus metadata, not telecom transport primitives.

## Lifecycles

1. Start session -> display/announce automated identity -> obtain recording consent if recording.
2. Accept message/audio -> validate channel event -> transcribe if needed.
3. Persist permitted transcript and safe context -> orchestration.
4. Obtain grounded response -> optional TTS -> send.
5. Repeat until termination/handoff/timeout.
6. End with outcome; persist no more personal data than necessary.

## Failure mode examples

- Microphone permission denied -> typed fallback immediately.
- STT confidence poor -> clarification; no booking mutation.
- Telephony disconnect during booking confirmation -> persist pending, do not commit until approved; reconcile any in-flight request by idempotency key.
- TTS fails -> show text and retry only with explicit control.
- Provider streaming format mismatch -> adapter performs codec/resampling, not LangGraph.
