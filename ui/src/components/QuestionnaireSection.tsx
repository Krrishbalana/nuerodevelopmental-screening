import { useEffect, useState } from "react";
import { getSessionQuestionnaire, questionnaireMeta } from "../api";
import type { QuestionnaireMeta, SessionQuestionnaire } from "../types";

const BAND_LABEL = { strong: "Strong", likely: "Likely", possible: "Possible", unlikely: "Unlikely" } as const;
const BAND_CLASS = { strong: "flagged", likely: "flagged", possible: "reported", unlikely: "not_flagged" } as const;

/**
 * Results of the parent questionnaire (Saathi engine, started from the camera findings).
 * Basic view until the adaptive report (step 3) replaces it.
 */
export function QuestionnaireSection({ sessionId, detailed = false }: { sessionId: string; detailed?: boolean }) {
  const [data, setData] = useState<SessionQuestionnaire | null | undefined>(undefined);
  const [meta, setMeta] = useState<QuestionnaireMeta | null>(null);

  useEffect(() => {
    getSessionQuestionnaire(sessionId).then(setData).catch(() => setData(null));
    questionnaireMeta().then(setMeta).catch(() => setMeta(null));
  }, [sessionId]);

  if (data === undefined) return null;
  if (data === null || !data.results) {
    return (
      <>
        <h2>Parent questions</h2>
        <p className="muted">
          Not answered yet.{" "}
          <a href={`?session=${encodeURIComponent(sessionId)}&questions=1`}>Answer the questions</a> to complete the
          report.
        </p>
      </>
    );
  }

  const r = data.results;
  const name = (key: string) => meta?.conditions.find((c) => c.key === key)?.short_name ?? key;
  const shown = r.conditions.filter((c) => c.band !== "unlikely");

  return (
    <>
      <h2>From your answers and the camera session</h2>
      <p className="muted small">
        {r.questions_asked} questions answered. Combined with what the camera saw by Omli's
        screening engine; its estimates are refined as more children are screened.
      </p>
      <div className={`outcome ${r.action === "urgent" || r.action === "refer" ? "alert" : r.action === "watch" ? "warn" : "good"}`}>
        <h3>{r.title}</h3>
        {shown.length > 0 ? (
          <ul className="findings">
            {shown.map((c) => (
              <li key={c.key}>
                <b>{name(c.key)}</b> <span className={`pill ${BAND_CLASS[c.band]}`}>{BAND_LABEL[c.band]}</span>
                {detailed && <span className="small"> {(c.probability * 100).toFixed(1)}%</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p>Nothing stood out from these answers.</p>
        )}
      </div>
      {r.steps.length > 0 && (
        <ol>
          {r.steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      )}

      {detailed && (
        <>
          <h3>Engine evidence</h3>
          <p className="muted small">Dataset {meta?.dataset_version} · {meta?.dataset_hash.slice(0, 12)}. Δ = change in log-odds.</p>
          {data.observations.length > 0 && (
            <table className="grid">
              <thead>
                <tr><th>Camera observation</th><th>Outcome</th><th>Condition</th><th>LR</th><th>Source</th></tr>
              </thead>
              <tbody>
                {data.observations.flatMap((o) =>
                  o.terms.map((t) => (
                    <tr key={o.id + t.condition}>
                      <td className="wrap">{o.label ?? o.id}</td>
                      <td>{o.outcome}</td>
                      <td>{name(t.condition)}</td>
                      <td>{t.lr}</td>
                      <td>{t.source} ({t.ref})</td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          )}
          {shown.map((c) => (
            <section key={c.key} className="metric">
              <h3>
                {name(c.key)} <span className={`pill ${BAND_CLASS[c.band]}`}>{BAND_LABEL[c.band]}</span>{" "}
                <span className="small">{(c.probability * 100).toFixed(1)}%</span>
              </h3>
              <p className="small muted">
                Strongest evidence:{" "}
                {c.evidence.slice(0, 6).map((e) => `${e.question_id} (${e.delta > 0 ? "+" : ""}${e.delta.toFixed(2)})`).join(", ")}
              </p>
            </section>
          ))}
        </>
      )}
    </>
  );
}
