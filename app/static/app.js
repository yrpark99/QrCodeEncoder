(() => {
  "use strict";

  const DEBOUNCE_MS = 200;

  const textEl = document.getElementById("text");
  const bytesEl = document.getElementById("bytes");
  const qrInfoEl = document.getElementById("qrinfo");
  const errorEl = document.getElementById("error");
  const resultEl = document.getElementById("result");
  const downloadBtn = document.getElementById("download");
  const settingsEl = document.getElementById("settings");
  const welcomeEl = document.getElementById("welcome");

  const encoder = new TextEncoder();
  let timer = null;
  let controller = null;
  let lastSvg = null;
  let objectUrl = null;
  let maxBytes = 4096;

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = false;
    resultEl.classList.add("stale");
  }

  function clearError() {
    errorEl.hidden = true;
    errorEl.textContent = "";
    resultEl.classList.remove("stale");
  }

  function setResult(node) {
    resultEl.replaceChildren(node);
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }

  function showPlaceholder() {
    const p = document.createElement("p");
    p.className = "placeholder";
    p.textContent = "QR code will appear here.";
    setResult(p);
    qrInfoEl.textContent = "";
    lastSvg = null;
    downloadBtn.disabled = true;
  }

  async function update() {
    const text = textEl.value;
    if (controller) controller.abort();

    if (text.length === 0) {
      clearError();
      showPlaceholder();
      return;
    }

    controller = new AbortController();
    try {
      const res = await fetch("/api/encode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // textarea.value always uses "\n" for line breaks.
        body: JSON.stringify({ text }),
        signal: controller.signal,
      });
      if (!res.ok) {
        let msg = `Error ${res.status}`;
        try { msg = (await res.json()).error || msg; } catch (_) { /* ignore */ }
        showError(msg);
        return;
      }
      const svg = await res.text();
      // Shown through <img>: the browser never runs scripts inside an SVG image.
      const img = document.createElement("img");
      img.alt = "QR code";
      setResult(img);
      objectUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
      img.src = objectUrl;
      lastSvg = svg;
      downloadBtn.disabled = false;
      const v = res.headers.get("X-QR-Version");
      const w = res.headers.get("X-QR-Width");
      qrInfoEl.textContent = v ? `Version ${v} (${w}×${w} modules)` : "";
      clearError();
    } catch (err) {
      if (err.name !== "AbortError") showError("Network error. Please try again.");
    }
  }

  textEl.addEventListener("input", () => {
    const n = encoder.encode(textEl.value).length;
    bytesEl.textContent = `${n} bytes`;
    bytesEl.style.color = n > maxBytes ? "var(--error-text)" : "";
    clearTimeout(timer);
    timer = setTimeout(update, DEBOUNCE_MS);
  });

  downloadBtn.addEventListener("click", () => {
    if (!lastSvg) return;
    const blob = new Blob(
      ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n', lastSvg],
      { type: "image/svg+xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "qrcode.svg";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  fetch("/api/info")
    .then((r) => r.json())
    .then((info) => {
      maxBytes = info.max_input_bytes;
      if (info.welcome) {
        welcomeEl.textContent = info.welcome;
        welcomeEl.hidden = false;
      }
      settingsEl.textContent =
        `libqrencode ${info.libqrencode}, EC level: ${info.level}, ` +
        `version: ${info.version === 0 ? "auto" : info.version}, mode: ${info.mode}, ` +
        `newline: ${info.newline.toUpperCase()}`;
    })
    .catch(() => {});
})();
