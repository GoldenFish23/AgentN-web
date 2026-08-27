import React, { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createRoot } from "react-dom/client";
import "./style.css";

const API_BASE = import.meta.env.VITE_API_URL || "";
const LEDGER_KEY = "agentn-flask-react-ledger-v2";

const fallbackRoles = {
  general: "Balanced conversational assistant",
  analyst: "Data-driven logic expert",
  visionary: "Futurist and blue-sky thinker",
  critic: "Skeptical auditor",
  engineer: "Systems architect",
  coder: "Software developer",
  economist: "Resource strategist",
  planner: "Project and logistics specialist",
  historian: "Historical analogy expert",
  philosopher: "Ethics and logic specialist",
  teacher: "Communication specialist",
  psychologist: "Behavioral expert",
  legal_counsel: "Regulatory specialist",
  mediator: "Consensus specialist",
};

function loadLedger() {
  try {
    return JSON.parse(localStorage.getItem(LEDGER_KEY) || "[]");
  } catch {
    return [];
  }
}

function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

function App() {
  const [query, setQuery] = useState("");
  const [sessions, setSessions] = useState(loadLedger);
  const [roles, setRoles] = useState(fallbackRoles);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("Ready");
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/roles`)
      .then((r) => r.json())
      .then((data) => {
        const map = {};
        for (const role of data.roles || []) map[role.id] = role.description;
        setRoles(map);
      })
      .catch(() => {});
  }, []);

  function save(next) {
    const trimmed = next.slice(-50);
    setSessions(trimmed);
    localStorage.setItem(LEDGER_KEY, JSON.stringify(trimmed));
  }

  async function ask(event) {
    event.preventDefault();
    const text = query.trim();
    if (!text || busy) return;

    setBusy(true);
    setError("");
    setSelected(null);
    setStage("Routing your question…");

    try {
      setStage("Consulting independent perspectives…");
      const response = await fetch(`${API_BASE}/api/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userInput: text,
          previousDecision: sessions.at(-1)?.finalSynthesis || null,
        }),
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Agent request failed.");

      const session = { ...data, userRequest: text };
      const next = [...sessions, session].slice(-50);
      save(next);
      setSelected(session);
      setQuery("");
      setStage("Consensus reached.");
    } catch (err) {
      setError(err.message || "Something went wrong.");
      setStage("Failed");
    } finally {
      setBusy(false);
    }
  }

  function clearLedger() {
    localStorage.removeItem(LEDGER_KEY);
    setSessions([]);
    setSelected(null);
  }

  const sessionCount = sessions.length;
  const truncationWarning = selected?.finalTruncated || selected?.experts?.some((x) => x.truncated);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo-mark"><span>✦</span></div>
          <div>
            <b>Agent<span>N</span></b>
            <small>Consensus intelligence</small>
          </div>
        </div>

        <button className="new-button" onClick={() => {
          setSelected(null);
          setQuery("");
        }}>
          <span>＋</span> New deliberation
        </button>

        <div className="ledger-title">
          <span>RECENT DELIBERATIONS</span>
          <button onClick={clearLedger}>Clear</button>
        </div>

        <div className="history">
          {[...sessions].reverse().map((s) => (
            <button
              className={`history-item ${selected?.sessionId === s.sessionId ? "active" : ""}`}
              key={s.sessionId}
              onClick={() => setSelected(s)}
            >
              <span>{s.userRequest}</span>
              <small>{new Date(s.timestamp).toLocaleString()}</small>
            </button>
          ))}
          {!sessionCount && (
            <div className="empty">
              <div className="empty-icon">◌</div>
              <span>Your deliberations will appear here.</span>
            </div>
          )}
        </div>

        <div className="footer-status">
          <div><span className="live-dot" /> Model online</div>
          <small>{selected?.model || "OpenRouter"}</small>
        </div>
      </aside>

      <main className="main">
        <header className="top">
          <div className="eyebrow"><span className="pulse" /> AGENTIC BOARDROOM</div>
          <div className="top-meta">
            <span className="meta-pill">MULTI-PERSPECTIVE</span>
            <span className="meta-pill subtle">v2</span>
          </div>
        </header>

        <div className="viewport">
          {!selected && !busy && (
            <section className="landing">
              <div className="hero-orbit" aria-hidden="true">
                <div className="orbit orbit-a" />
                <div className="orbit orbit-b" />
                <div className="core">N</div>
              </div>
              <div className="hero-copy">
                <div className="kicker">ASK ONCE. THINK TOGETHER.</div>
                <h1>One question.<br /><em>Many minds.</em> One answer.</h1>
                <p>
                  AgentN routes your problem to the perspectives that matter,
                  then synthesizes their strongest ideas into one clear response.
                </p>
              </div>

              <div className="examples">
                {[
                  "What's the best place in Delhi to visit under ₹350?",
                  "What technology is booming, free to learn, and sellable?",
                  "Build a 5-day Kanpur history trip with practical costs.",
                ].map((example) => (
                  <button key={example} onClick={() => setQuery(example)}>
                    <span>{example}</span><b>↗</b>
                  </button>
                ))}
              </div>
            </section>
          )}

          {busy && (
            <section className="progress">
              <div className="thinking-ring"><span /></div>
              <div className="progress-copy">
                <div className="kicker">DELIBERATION IN PROGRESS</div>
                <h2>{stage}</h2>
                <p>Independent roles are reasoning in parallel before the mediator forms the final synthesis.</p>
              </div>
              <div className="signal-grid">
                {["ROUTE", "PERSPECTIVES", "SYNTHESIS"].map((x, i) => (
                  <div className="signal" key={x}>
                    <span>{String(i + 1).padStart(2, "0")}</span>{x}
                  </div>
                ))}
              </div>
          </section>
          )}

          {selected && !busy && (
            <section className="result">
              <div className="result-hero">
                <div>
                  <div className="kicker">DELIBERATION {selected.sessionId}</div>
                  <h1>{selected.userRequest}</h1>
                </div>
                <div className="result-time">{new Date(selected.timestamp).toLocaleString()}</div>
              </div>

              <div className="router-card">
                <div className="router-main">
                  <div className="section-label">ROUTER SIGNAL</div>
                  <p>{selected.routingLogic}</p>
                </div>
                <div className="chips">
                  {selected.selectedExperts.map((role) => <span key={role}>{role}</span>)}
                </div>
              </div>

              {truncationWarning && (
                <div className="warning">
                  <span>⚠</span>
                  <div><b>Generation limit reached</b><small>One or more model outputs ended at the provider limit. Increase the configured token budget for even longer answers.</small></div>
                </div>
              )}

              <div className="section-head">
                <div>
                  <div className="kicker">THE PANEL</div>
                  <h2>Independent perspectives</h2>
                </div>
                <small>{selected.experts.length} voices</small>
              </div>

              <div className="panel">
                {selected.experts.map((expert) => (
                  <article className="expert" key={expert.role}>
                    <div className="expert-head">
                      <div className="role-icon">{expert.role[0].toUpperCase()}</div>
                      <div className="role-meta">
                        <b>{expert.role}</b>
                        <small>{roles[expert.role]}</small>
                      </div>
                      {expert.truncated && <span className="tiny-warning">LIMIT</span>}
                    </div>
                    <div className="output"><Markdown>{expert.output}</Markdown></div>
                  </article>
                ))}
              </div>

              <div className="consensus">
                <div className="consensus-head">
                  <div>
                    <div className="kicker">MEDIATOR</div>
                    <h2>Consensus synthesis</h2>
                  </div>
                  <span className="consensus-badge">✦ FINAL</span>
                </div>
                <div className="final-answer">
                  <Markdown>{selected.finalSynthesis}</Markdown>
                </div>
              </div>
            </section>
          )}
        </div>

        {error && <div className="error"><span>!</span>{error}</div>}

        <form className="composer" onSubmit={ask}>
          <div className="composer-shell">
            <div className="composer-icon">✦</div>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={busy}
              placeholder="Ask AgentN anything…"
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === "Enter") ask(e);
              }}
            />
            <button disabled={busy || !query.trim()} aria-label="Send question">
              {busy ? <span className="button-spinner" /> : "Ask AgentN"} <b>↗</b>
            </button>
          </div>
          <div className="composer-hint">
            <span>Multi-agent reasoning • Markdown-aware • Long-form synthesis</span>
            <kbd>⌘</kbd><kbd>ENTER</kbd>
          </div>
        </form>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode><App /></React.StrictMode>
);
