import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import Logo from "../components/Logo";

export default function AuthPage({ mode }) {
  const { user, login, signup } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", password: "", display_name: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const isSignup = mode === "signup";
  const dest = location.state?.from || "/dugout";

  if (user) return <Navigate to={dest} replace />;

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (isSignup) await signup(form);
      else await login({ email: form.email, password: form.password });
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card form" onSubmit={submit}>
        <div className="auth-head">
          <Logo size={40} />
          <h2 className="page-title">{isSignup ? "Create your account" : "Welcome back"}</h2>
        </div>
        {isSignup && (
          <label className="field">
            <span>Your name</span>
            <input value={form.display_name} onChange={set("display_name")} required maxLength={80} autoFocus />
          </label>
        )}
        <label className="field">
          <span>Email</span>
          <input type="email" value={form.email} onChange={set("email")} required autoFocus={!isSignup} autoComplete="email" />
        </label>
        <label className="field">
          <span>Password{isSignup && " (8+ characters)"}</span>
          <input
            type="password"
            value={form.password}
            onChange={set("password")}
            required
            minLength={isSignup ? 8 : undefined}
            autoComplete={isSignup ? "new-password" : "current-password"}
          />
        </label>
        {error && <p className="small error-text" role="alert">{error}</p>}
        <button className="btn primary big" type="submit" disabled={busy}>
          {busy ? "One moment…" : isSignup ? "Create account" : "Sign in"}
        </button>
        <p className="small muted center">
          {isSignup ? (
            <>
              Already have an account? <Link to="/login" state={location.state}>Sign in</Link>
            </>
          ) : (
            <>
              New here? <Link to="/signup" state={location.state}>Create an account</Link>
            </>
          )}
        </p>
        {import.meta.env.DEV && !isSignup && (
          <p className="small muted center demo-hint">
            Local demo: <code>demo@pitchlab.dev</code> / <code>pitchlab-demo</code> (created by{" "}
            <code>python -m app.seed</code>)
          </p>
        )}
      </form>
    </div>
  );
}
