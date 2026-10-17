import { useState } from "react";
import { api } from "../api";

export default function UploadCsv({ onUploaded }) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setStatus(null);
    try {
      const r = await api.uploadStatcast(file);
      setStatus({ ok: true, text: `Loaded ${r.pitches.toLocaleString()} pitches across ${r.appearances} games` });
      onUploaded();
    } catch (err) {
      setStatus({ ok: false, text: err.message });
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  return (
    <div className="upload">
      <h4>Import data</h4>
      <p className="muted small">
        Statcast CSV from Baseball Savant, or your own bullpen data in the same columns.
        Pitchers you upload are private to your account and added to your dugout.
      </p>
      <label className={busy ? "upload-btn disabled" : "upload-btn"}>
        {busy ? "Uploading…" : "Upload CSV"}
        <input type="file" accept=".csv,text/csv" onChange={handleFile} disabled={busy} hidden />
      </label>
      {status && <p className={status.ok ? "small ok" : "small error-text"}>{status.text}</p>}
    </div>
  );
}
