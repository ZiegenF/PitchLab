import { useState } from "react";
import { api } from "../api";

const COUNT_FIELDS = [
  ["hits", "H"],
  ["runs", "R"],
  ["earned_runs", "ER"],
  ["walks", "BB"],
  ["strikeouts", "K"],
  ["home_runs", "HR"],
  ["hit_by_pitch", "HBP"],
];

const today = () => new Date().toISOString().slice(0, 10);
const blank = () => ({
  game_date: today(),
  opponent: "",
  is_start: true,
  innings_pitched: "",
  batters_faced: "",
  ...Object.fromEntries(COUNT_FIELDS.map(([k]) => [k, ""])),
});

// Enter a box-score line by hand (from a scorebook, GameChanger, etc.).
export default function GameForm({ pitcherId, onSaved, onCancel }) {
  const [form, setForm] = useState(blank);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.addGame(pitcherId, {
        game_date: form.game_date,
        opponent: form.opponent.trim().toUpperCase(),
        is_start: form.is_start,
        innings_pitched: form.innings_pitched.trim(),
        batters_faced: form.batters_faced === "" ? null : Number(form.batters_faced),
        ...Object.fromEntries(COUNT_FIELDS.map(([k]) => [k, Number(form[k] || 0)])),
      });
      setForm(blank());
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="game-form" onSubmit={submit}>
      <div className="game-form-grid">
        <label className="field">
          <span>Date</span>
          <input type="date" value={form.game_date} onChange={set("game_date")} required />
        </label>
        <label className="field">
          <span>Opponent</span>
          <input value={form.opponent} onChange={set("opponent")} placeholder="BOS" maxLength={10} />
        </label>
        <label className="field">
          <span>IP</span>
          <input
            value={form.innings_pitched}
            onChange={set("innings_pitched")}
            placeholder="6.2"
            pattern="\d{1,2}(\.[012])?"
            title="Innings like 6, 6.1 or 6.2 (thirds of an inning)"
            required
            inputMode="decimal"
          />
        </label>
        {COUNT_FIELDS.map(([k, label]) => (
          <label className="field narrow" key={k}>
            <span>{label}</span>
            <input type="number" min="0" value={form[k]} onChange={set(k)} placeholder="0" />
          </label>
        ))}
        <label className="field narrow">
          <span>BF</span>
          <input
            type="number"
            min="0"
            value={form.batters_faced}
            onChange={set("batters_faced")}
            placeholder="auto"
            title="Batters faced. Leave blank to estimate from outs + hits + walks + HBP"
          />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={form.is_start} onChange={set("is_start")} />
          Started
        </label>
      </div>
      {error && <p className="small error-text" role="alert">{error}</p>}
      <div className="form-actions">
        <span className="spacer" />
        <button type="button" className="btn ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "Saving…" : "Add game"}
        </button>
      </div>
    </form>
  );
}
