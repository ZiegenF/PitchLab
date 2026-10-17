import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export default function TrackButton({ pitcher, onChange }) {
  const { user } = useAuth();
  const location = useLocation();
  const [busy, setBusy] = useState(false);

  if (!user) {
    return (
      <Link className="btn ghost" to="/login" state={{ from: location.pathname }}>
        Sign in to track
      </Link>
    );
  }

  async function toggle() {
    setBusy(true);
    try {
      await (pitcher.is_tracked ? api.untrack(pitcher.id) : api.track(pitcher.id));
      onChange?.(!pitcher.is_tracked);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      className={pitcher.is_tracked ? "btn tracked" : "btn primary"}
      onClick={toggle}
      disabled={busy}
      aria-pressed={pitcher.is_tracked}
    >
      {pitcher.is_tracked ? "✓ In my dugout" : "+ Add to dugout"}
    </button>
  );
}
