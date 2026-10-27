import { useEffect, useState } from "react";
import { questionnaireMeta } from "../api";
import { AGE_MONTHS } from "../config";
import type { Intake, QuestionnaireMeta } from "../types";

export function ageInMonths(dob: string, today = new Date()): number {
  const days = (today.getTime() - new Date(dob).getTime()) / 86_400_000;
  return days / 30.4375;
}

const CONSENTS = [
  "I am this child's parent or legal guardian and I agree to this check.",
  "I understand the camera and microphone are used during the session. Video and audio are processed on this device; only measurements (like head direction) are sent, unless I choose below to save the recording.",
  "I understand this is a screening, not a diagnosis.",
];

export function Setup({ onStart }: { onStart: (dob: string, saveRecording: boolean, intake: Intake) => void }) {
  const [dob, setDob] = useState("");
  const [agreed, setAgreed] = useState(CONSENTS.map(() => false));
  const [saveRecording, setSaveRecording] = useState(false);
  const [intake, setIntake] = useState<Intake>({ sex: "na", born: "term", familyFactors: [] });
  const [meta, setMeta] = useState<QuestionnaireMeta | null>(null);

  useEffect(() => {
    questionnaireMeta().then(setMeta).catch(() => setMeta(null));
  }, []);

  const toggleFactor = (factor: string, on: boolean) =>
    setIntake((v) => ({
      ...v,
      familyFactors: on ? [...v.familyFactors, factor] : v.familyFactors.filter((f) => f !== factor),
    }));

  const age = dob ? ageInMonths(dob) : null;
  const ageOk = age !== null && age >= AGE_MONTHS.min && age <= AGE_MONTHS.max;
  const ready = ageOk && agreed.every(Boolean);

  return (
    <div className="panel">
      <h1>Behavior screening</h1>
      <p className="muted">
        A 3-minute check with your child, then a few questions for you. Your child watches short videos while the camera
        notices where they look and how they respond to their name; your answers to the questions that follow depend on
        what the camera saw.
      </p>

      <label className="field">
        <span>Child's date of birth</span>
        <input type="date" value={dob} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDob(e.target.value)} />
      </label>
      {age !== null && !ageOk && (
        <p className="error">
          This check is for children aged {AGE_MONTHS.min} months to {AGE_MONTHS.max / 12} years.
        </p>
      )}

      <div className="intake">
        <label className="field">
          <span>Child is a</span>
          <select id="intake-sex" value={intake.sex} onChange={(e) => setIntake({ ...intake, sex: e.target.value as Intake["sex"] })}>
            <option value="na">Prefer not to say</option>
            <option value="boy">Boy</option>
            <option value="girl">Girl</option>
          </select>
        </label>
        <label className="field">
          <span>Born</span>
          <select id="intake-born" value={intake.born} onChange={(e) => setIntake({ ...intake, born: e.target.value as Intake["born"] })}>
            <option value="term">At full term (37 weeks or later)</option>
            <option value="32_36">Early, at 32–36 weeks</option>
            <option value="lt32">Very early, before 32 weeks</option>
          </select>
        </label>
      </div>
      {meta && meta.family_factors.length > 0 && (
        <fieldset className="family">
          <legend>In the family (tick any that apply)</legend>
          {meta.family_factors.map((f) => (
            <label key={f.factor} className="check">
              <input
                type="checkbox"
                id={`family-${f.factor}`}
                checked={intake.familyFactors.includes(f.factor)}
                onChange={(e) => toggleFactor(f.factor, e.target.checked)}
              />
              <span>{f.label}</span>
            </label>
          ))}
        </fieldset>
      )}

      <div className="consents">
        {CONSENTS.map((text, i) => (
          <label key={i} className="check">
            <input
              type="checkbox"
              checked={agreed[i]}
              onChange={(e) => setAgreed(agreed.map((v, j) => (j === i ? e.target.checked : v)))}
            />
            <span>{text}</span>
          </label>
        ))}
      </div>

      <div className="optional-consent">
        <label className="check">
          <input type="checkbox" checked={saveRecording} onChange={(e) => setSaveRecording(e.target.checked)} />
          <span>
            <b>Optional:</b> save the camera recording (video and sound) with this session, so the analysis can be replayed
            later and reviewed by a clinician. You can delete it from the report at any time. If you leave this unticked,
            the recording stays on this device only and is gone when you close the page.
          </span>
        </label>
      </div>

      <h2>Before you start</h2>
      <ul className="muted">
        <li>Sit in a well-lit room with the light on your child's face, not behind them.</li>
        <li>Your child sits about an arm's length from the screen (on your lap is fine for now).</li>
        <li>Turn off the TV and other sounds. Keep toys out of reach.</li>
      </ul>

      <button className="primary" disabled={!ready} onClick={() => onStart(dob, saveRecording, intake)}>
        Next: camera check
      </button>
    </div>
  );
}
