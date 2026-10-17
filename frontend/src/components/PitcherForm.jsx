import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import Avatar from "./Avatar";
import { COLLEGE_CLASSES, LEVELS, LEVEL_LABEL, affiliationField } from "../levels";

const EMPTY = {
  name: "", team: "", throws: "R", role: "SP", hometown: "",
  level: "", class_year: "", affiliation: "", in_portal: false,
};

// Create a pitcher (pitcher == null) or edit an existing one, including the photo.
export default function PitcherForm({ open, pitcher, onClose, onSaved, onDeleted }) {
  const dialogRef = useRef(null);
  const [form, setForm] = useState(EMPTY);
  const [photoFile, setPhotoFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [removePhoto, setRemovePhoto] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const d = dialogRef.current;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
    if (open) {
      setForm(
        pitcher
          ? {
              ...EMPTY,
              ...pitcher,
              hometown: pitcher.hometown ?? "",
              level: pitcher.level ?? "",
              class_year: pitcher.class_year ?? "",
              affiliation: pitcher.affiliation ?? "",
              in_portal: !!pitcher.in_portal,
            }
          : EMPTY
      );
      setPhotoFile(null);
      setRemovePhoto(false);
      setConfirmDelete(false);
      setError(null);
    }
  }, [open, pitcher]);

  // object URLs must be released or they leak
  useEffect(() => {
    if (!photoFile) return setPreview(null);
    const url = URL.createObjectURL(photoFile);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photoFile]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setLevel = (e) => setForm((f) => ({ ...f, level: e.target.value, class_year: "", affiliation: "", in_portal: false }));
  const aff = affiliationField(form.level);
  const shownPhoto = preview ?? (removePhoto ? null : pitcher?.photo_url);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: form.name.trim(),
        team: form.team.trim().toUpperCase(),
        throws: form.throws,
        role: form.role,
        hometown: form.hometown.trim() || null,
        level: form.level || null,
        class_year: form.class_year.trim().toUpperCase() || null,
        affiliation: aff ? form.affiliation.trim() || null : null,
        in_portal: form.level === "NCAA" && form.in_portal,
      };
      let saved = pitcher
        ? await api.updatePitcher(pitcher.id, body)
        : await api.createPitcher(body);
      if (photoFile) saved = await api.uploadPhoto(saved.id, photoFile);
      else if (removePhoto && pitcher?.photo_url) saved = await api.deletePhoto(saved.id);
      onSaved(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirmDelete) return setConfirmDelete(true);
    setBusy(true);
    try {
      await api.deletePitcher(pitcher.id);
      onDeleted(pitcher.id);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <dialog ref={dialogRef} className="modal" onClose={onClose} onCancel={onClose}>
      <form onSubmit={submit} className="form">
        <h3>{pitcher ? `Edit ${pitcher.name}` : "Add pitcher"}</h3>

        <div className="photo-row">
          <Avatar name={form.name || "?"} src={shownPhoto} size={72} />
          <div className="photo-actions">
            <label className="btn">
              {shownPhoto ? "Change photo" : "Add photo"}
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                hidden
                onChange={(e) => {
                  setPhotoFile(e.target.files?.[0] ?? null);
                  setRemovePhoto(false);
                  e.target.value = "";
                }}
              />
            </label>
            {shownPhoto && (
              <button
                type="button"
                className="btn ghost"
                onClick={() => {
                  setPhotoFile(null);
                  setRemovePhoto(true);
                }}
              >
                Remove
              </button>
            )}
            <span className="muted small">JPEG, PNG, WebP or GIF, up to 5 MB</span>
          </div>
        </div>

        <label className="field">
          <span>Name</span>
          <input value={form.name} onChange={set("name")} required maxLength={100} autoFocus />
        </label>
        <label className="field">
          <span>Hometown</span>
          <input
            value={form.hometown}
            onChange={set("hometown")}
            placeholder="City, State or Country"
            maxLength={120}
          />
        </label>
        <div className="field-row">
          <label className="field">
            <span>Team</span>
            <input
              value={form.team}
              onChange={set("team")}
              placeholder={form.level === "HS" ? "LAKESIDE" : form.level === "NCAA" ? "BYU" : "NYY"}
              maxLength={10}
            />
          </label>
          <label className="field">
            <span>Throws</span>
            <select value={form.throws} onChange={set("throws")}>
              <option value="R">Right</option>
              <option value="L">Left</option>
            </select>
          </label>
          <label className="field">
            <span>Role</span>
            <select value={form.role} onChange={set("role")}>
              <option value="SP">Starter</option>
              <option value="RP">Reliever</option>
            </select>
          </label>
        </div>

        <div className="field-row">
          <label className="field">
            <span>Level</span>
            <select value={form.level} onChange={setLevel}>
              <option value="">Not set</option>
              {[...LEVELS].reverse().map((l) => (
                <option key={l} value={l}>
                  {LEVEL_LABEL[l]}
                </option>
              ))}
            </select>
          </label>
          {form.level === "NCAA" && (
            <label className="field">
              <span>Class</span>
              <select value={form.class_year} onChange={set("class_year")}>
                <option value="">Not set</option>
                {COLLEGE_CLASSES.map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          )}
          {form.level === "HS" && (
            <label className="field">
              <span>Grad year</span>
              <input
                value={form.class_year}
                onChange={set("class_year")}
                placeholder="2027"
                inputMode="numeric"
                pattern="\d{4}"
                maxLength={4}
              />
            </label>
          )}
          {aff && (
            <label className="field">
              <span>{aff.label}</span>
              <input value={form.affiliation} onChange={set("affiliation")} placeholder={aff.placeholder} maxLength={60} />
            </label>
          )}
        </div>
        {form.level === "NCAA" && (
          <label className="check">
            <input
              type="checkbox"
              checked={form.in_portal}
              onChange={(e) => setForm((f) => ({ ...f, in_portal: e.target.checked }))}
            />
            In the transfer portal
          </label>
        )}

        {error && <p className="small error-text" role="alert">{error}</p>}

        <div className="form-actions">
          {pitcher && (
            <button type="button" className="btn danger" onClick={handleDelete} disabled={busy}>
              {confirmDelete ? "Delete pitcher and all their data?" : "Delete"}
            </button>
          )}
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={busy}>
            {busy ? "Saving…" : pitcher ? "Save" : "Add pitcher"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
