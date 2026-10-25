"use strict";

const browserInfo = document.querySelector("#browser-info");
const microphoneStatus = document.querySelector("#microphone-status");
const recognitionStatus = document.querySelector("#recognition-status");
const speechStatus = document.querySelector("#speech-status");
const speechText = document.querySelector("#speech-text");
const startRecognition = document.querySelector("#start-recognition");
const stopRecognition = document.querySelector("#stop-recognition");

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;

browserInfo.textContent =
  `${navigator.userAgent} | secure context: ${window.isSecureContext ? "yes" : "no"} | ` +
  `speech recognition API: ${SpeechRecognition ? "available" : "unavailable"} | ` +
  `speech synthesis API: ${window.speechSynthesis ? "available" : "unavailable"}`;

document.querySelector("#check-microphone").addEventListener("click", async () => {
  if (!navigator.mediaDevices?.getUserMedia) {
    microphoneStatus.textContent =
      "FAIL: microphone capture is unavailable in this browser context.";
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    for (const track of stream.getTracks()) {
      track.stop();
    }
    microphoneStatus.textContent =
      "PASS: microphone permission granted; test stream stopped without recording.";
  } catch (error) {
    microphoneStatus.textContent =
      `FAIL: microphone permission/capture error: ${error.name || "unknown error"}.`;
  }
});

startRecognition.addEventListener("click", () => {
  if (!SpeechRecognition) {
    recognitionStatus.textContent =
      "UNAVAILABLE: this Chrome installation does not expose SpeechRecognition.";
    return;
  }
  if (recognition) {
    recognitionStatus.textContent = "Recognition is already running.";
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "en-US";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  startRecognition.disabled = true;
  stopRecognition.disabled = false;
  recognitionStatus.textContent =
    "Listening once. Speak only the harmless test phrase.";

  recognition.onresult = (event) => {
    const result = event.results[0]?.[0];
    if (!result) {
      recognitionStatus.textContent = "FAIL: recognition returned no result.";
      return;
    }
    speechText.value = result.transcript;
    const confidence = Number.isFinite(result.confidence)
      ? result.confidence.toFixed(2)
      : "unavailable";
    recognitionStatus.textContent =
      `Result received (browser confidence ${confidence}). ` +
      "Verify the words yourself; confidence is not a compatibility pass by itself.";
  };
  recognition.onerror = (event) => {
    recognitionStatus.textContent =
      `FAIL: recognition error: ${event.error || "unknown error"}.`;
  };
  recognition.onend = () => {
    recognition = null;
    startRecognition.disabled = false;
    stopRecognition.disabled = true;
  };

  try {
    recognition.start();
  } catch (error) {
    recognitionStatus.textContent =
      `FAIL: could not start recognition: ${error.name || "unknown error"}.`;
    recognition = null;
    startRecognition.disabled = false;
    stopRecognition.disabled = true;
  }
});

stopRecognition.addEventListener("click", () => {
  recognition?.stop();
});

document.querySelector("#speak-text").addEventListener("click", () => {
  if (!window.speechSynthesis) {
    speechStatus.textContent = "UNAVAILABLE: speech synthesis is not supported.";
    return;
  }
  const text = speechText.value.trim();
  if (!text) {
    speechStatus.textContent = "FAIL: enter or recognize test text before speaking.";
    return;
  }

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.onstart = () => {
    speechStatus.textContent = "Speaking; confirm that audio is audible.";
  };
  utterance.onend = () => {
    speechStatus.textContent =
      "Speech synthesis finished; human confirmation of audibility is still required.";
  };
  utterance.onerror = (event) => {
    speechStatus.textContent =
      `FAIL: speech synthesis error: ${event.error || "unknown error"}.`;
  };
  window.speechSynthesis.speak(utterance);
});

document.querySelector("#stop-speech").addEventListener("click", () => {
  window.speechSynthesis?.cancel();
  speechStatus.textContent = "Speech stopped.";
});
