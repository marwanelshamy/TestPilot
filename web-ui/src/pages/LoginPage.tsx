import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
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
      <form className="card login-card" onSubmit={submit}>
        <h1>
          TestPilot <span>AI</span>
        </h1>
        <p className="muted">AI suggests tests. People approve them. The real test runner decides pass or fail.</p>
        <ErrorBanner error={error} />
        <label>
          E-mail
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <div className="demo">
          Demo accounts:{" "}
          {DEMO.map(([mail, label]) => (
            <button type="button" className="link" key={mail} onClick={() => setEmail(mail)}>
              {label}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
