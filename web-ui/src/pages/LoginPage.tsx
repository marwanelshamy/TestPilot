import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Flask, Logo, Shield, Sparkles } from "../components/icons";
import { ErrorBanner } from "../components/ui";

const DEMO = [
  ["dev@testpilot.local", "Developer"],
  ["qa@testpilot.local", "QA Assistant"],
  ["lead@testpilot.local", "Team Lead"],
];

export function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/projects" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      nav("/projects");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <section className="login-hero" aria-hidden>
        <span className="orb a" />
        <span className="orb b" />
        <span className="orb c" />
        <div className="brand" style={{ padding: 0 }}>
          <span className="brand-mark"><Logo size={20} /></span>
          <span className="brand-name">TestPilot <span>AI</span></span>
        </div>
        <div>
          <h1 className="hero-title">
            Tests that <span className="grad-text">AI suggests</span>,<br />people approve,<br />and reality decides.
          </h1>
          <ul className="hero-points">
            <li>
              <span className="ic"><Sparkles /></span>
              <span><b>Suggest</b>Turn requirements into normal, boundary and negative pytest cases.</span>
            </li>
            <li>
              <span className="ic"><Shield /></span>
              <span><b>Approve</b>Nothing runs until a human approves that exact version.</span>
            </li>
            <li>
              <span className="ic"><Flask /></span>
              <span><b>Run safely</b>Every run in a fresh, locked-down sandbox — pass or fail comes from pytest, never from the AI.</span>
            </li>
          </ul>
        </div>
        <p className="small" style={{ color: "#8d89a3", margin: 0 }}>CSE4203 · Milestone 3 prototype</p>
      </section>

      <div className="login-side">
        <form className="login-card" onSubmit={submit}>
          <div>
            <h2>Welcome back</h2>
            <p className="muted" style={{ margin: ".3rem 0 0" }}>Sign in to your testing workspace.</p>
          </div>
          <ErrorBanner error={error} />
          <label className="field">
            E-mail
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus placeholder="you@team.dev" />
          </label>
          <label className="field">
            Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="••••••••" />
          </label>
          <button type="submit" className="primary" disabled={busy} style={{ padding: ".75rem" }}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <div>
            <div className="small faint" style={{ marginBottom: ".45rem" }}>Try a demo account</div>
            <div className="demo-chips">
              {DEMO.map(([mail, label]) => (
                <button
                  type="button"
                  className="demo-chip"
                  key={mail}
                  aria-pressed={email === mail}
                  onClick={() => setEmail(mail)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
