async function sendRequest() {
  const resultEl = document.getElementById("result");

  // ── Gather inputs ──────────────────────────────────────
  const identifier     = document.getElementById("identifier").value.trim();
  const limit          = parseInt(document.getElementById("limit").value);
  const window_seconds = parseInt(document.getElementById("window").value);
  const algorithm      = document.getElementById("algorithm").value;
  const apiKey         = document.getElementById("apikey").value.trim();

  // ── Validation ─────────────────────────────────────────
  if (!identifier || !apiKey) {
    setResult("⚠  Identifier and API Key are required.", "warn");
    return;
  }
  if (isNaN(limit) || isNaN(window_seconds) || limit <= 0 || window_seconds <= 0) {
    setResult("⚠  Limit and Window must be positive numbers.", "warn");
    return;
  }

  // ── Loading state ──────────────────────────────────────
  const btn = document.querySelector("button");
  btn.disabled = true;
  btn.textContent = "↳ Sending…";
  setResult("Awaiting response…", "muted");

  // ── Request ────────────────────────────────────────────
  try {
    const response = await fetch("https://ratelock.onrender.com/v1/check", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify({ identifier, limit, window_seconds, algorithm }),
    });

    const data = await response.json();
    const pretty = JSON.stringify(data, null, 2);

    // Color-code by allowed / denied / error status
    if (!response.ok) {
      setResult(pretty, "error");
    } else if (data.allowed === false) {
      setResult(pretty, "denied");
    } else {
      setResult(pretty, "ok");
    }

  } catch (err) {
    setResult(`✕  Network error: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "↳ Check Rate Limit";
  }
}

// ── Result renderer ────────────────────────────────────────
function setResult(text, state = "muted") {
  const el = document.getElementById("result");
  el.textContent = text;

  const colors = {
    ok:     "#86efac",   // green  — allowed
    denied: "#fbbf24",   // amber  — rate limited
    warn:   "#fcd34d",   // yellow — validation
    error:  "#f87171",   // red    — network / server error
    muted:  "#3a4358",   // dim    — idle
  };

  el.style.color = colors[state] ?? colors.muted;
}