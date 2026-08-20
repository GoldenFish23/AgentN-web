import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const LEDGER_KEY = "agentn-flask-react-ledger-v1";

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
  mediator: "Consensus specialist"
};

function loadLedger() {
  try {
    return JSON.parse(localStorage.getItem(LEDGER_KEY) || "[]");
  } catch {
    return [];
  }
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
    fetch("/api/roles")
      .then(r => r.json())
      .then(data => {
        const map = {};
        for (const role of data.roles) map[role.id] = role.description;
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
      const response = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userInput: text,
          previousDecision: sessions.at(-1)?.finalSynthesis || null
        })
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Agent request failed.");

      const session = {
        ...data,
        userRequest: text
      };

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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">A</div>
          <div>
            <b>AgentN</b>
            <small>Multi-role deliberation</small>
          </div>
        </div>

        <button className="new-button" onClick={() => {
          setSelected(null);
          setQuery("");
        }}>
          + New question
        </button>

        <div className="ledger-title">
          <span>SESSION LEDGER</span>
          <button onClick={clearLedger}>Clear</button>
        </div>

        <div className="history">
          {[...sessions].reverse().map(s => (
            <button
              className={`history-item ${selected?.sessionId === s.sessionId ? "active" : ""}`}
              key={s.sessionId}
              onClick={() => setSelected(s)}
            >
              <span>{s.userRequest}</span>
              <small>{new Date(s.timestamp).toLocaleString()}</small>
            </button>
          ))}
          {!sessions.length && <div className="empty">No sessions yet.</div>}
        </div>

        <div className="footer-status">
          <span className="live-dot" />
          OpenRouter
          <small>Nemotron free</small>
        </div>
      </aside>

      <main className="main">
        <header className="top">
          <div>
            <label>AGENTIC BOARDROOM</label>
            <h1>Ask one question.<br /><i>Hear several minds.</i></h1>
          </div>
          <div className="status">
            <span className="live-dot" /> {busy ? stage : "System ready"}
          </div>
        </header>

        {!selected && !busy && (
          <section className="landing">
            <p>
              AgentN routes a question to the roles that add unique value,
              collects independent perspectives, and asks a mediator to
              produce one consensus answer.
            </p>

            <div className="examples">
              {[
                "What's the best place in Delhi to visit?",
                "Should I learn Python or JavaScript first?",
                "Design a small SaaS architecture."
              ].map(example => (
                <button key={example} onClick={() => setQuery(example)}>
                  {example}
                  <span>→</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {busy && (
          <section className="progress">
            <div className="spinner" />
            <div>
              <label>DELIBERATION IN PROGRESS</label>
              <h2>{stage}</h2>
              <p>Independent roles are being consulted before the mediator writes the final answer.</p>
            </div>
          </section>
        )}

        {selected && !busy && (
          <section className="result">
            <div className="question">
              <label>USER QUESTION</label>
              <h2>{selected.userRequest}</h2>
            </div>

            <div className="router-card">
              <div>
                <label>ROUTER</label>
                <p>{selected.routingLogic}</p>
              </div>
              <div className="chips">
                {selected.selectedExperts.map(role => <span key={role}>{role}</span>)}
              </div>
            </div>

            <div className="section-head">
              <span>THE PANEL</span>
              <small>{selected.experts.length} perspectives</small>
            </div>

            <div className="panel">
              {selected.experts.map(expert => (
                <article className="expert" key={expert.role}>
                  <div className="expert-head">
                    <div className="role-icon">{expert.role[0].toUpperCase()}</div>
                    <div>
                      <b>{expert.role}</b>
                      <small>{roles[expert.role]}</small>
                    </div>
                  </div>
                  <div className="output">{expert.output}</div>
                </article>
              ))}
            </div>

            <div className="consensus">
              <div className="consensus-head">
                <label>MEDIATOR</label>
                <span>CONSENSUS</span>
              </div>
              <div className="final-answer">{selected.finalSynthesis}</div>
            </div>
          </section>
        )}

        {error && <div className="error">{error}</div>}

        <form className="composer" onSubmit={ask}>
          <textarea
            value={query}
            onChange={e => setQuery(e.target.value)}
            disabled={busy}
            placeholder="Ask AgentN anything…"
            onKeyDown={e => {
              if ((e.ctrlKey || e.metaKey) && e.key === "Enter") ask(e);
            }}
          />
          <div className="composer-bottom">
            <small>Ctrl / ⌘ + Enter</small>
            <button disabled={busy || !query.trim()}>
              {busy ? "Deliberating…" : "Ask AgentN →"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode><App /></React.StrictMode>
);
