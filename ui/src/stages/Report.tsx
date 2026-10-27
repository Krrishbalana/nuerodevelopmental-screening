import { useEffect, useRef, useState } from "react";
import { deleteRecording, getFullReport, getSavedRecording } from "../api";
import type { RecordingStatus } from "../App";
import { DomainWheel } from "../components/DomainWheel";
import type { ReplayMedia } from "../replay/data";
import type { AutismWheel as AutismWheelData, ConditionSection, Finding, FullReport, MetricResult, MetricStatus, Report as ReportData } from "../types";
import { Replay } from "./Replay";

const ACTION_CLASS = { urgent: "alert", refer: "alert", watch: "warn", on_track: "good" } as const;
const BAND_LABEL = { strong: "Strong signs", likely: "Likely", possible: "Possible", unlikely: "Unlikely" } as const;
const BAND_CLASS = { strong: "flagged", likely: "flagged", possible: "reported", unlikely: "not_flagged" } as const;
const STATUS_LABEL: Record<MetricStatus, string> = { flagged: "Sign seen", not_flagged: "Not seen", insufficient: "Not measured" };

export function Report({
  report,
  sessionId,
  replayMedia = null,
  recordingStatus = null,
}: {
  report: ReportData;
  sessionId: string;
  replayMedia?: ReplayMedia | null;
  recordingStatus?: RecordingStatus;
}) {
  const [view, setView] = useState<"parent" | "clinician">("parent");
  const [replay, setReplay] = useState(false);
  const [saved, setSaved] = useState<ReplayMedia | null>(null);
  const [status, setStatus] = useState<RecordingStatus>(recordingStatus);
  const [full, setFull] = useState<FullReport | null>(null);
  const [error, setError] = useState("");
  const [pdfBusy, setPdfBusy] = useState(false);
  const body = useRef<HTMLDivElement>(null);

  useEffect(() => setStatus(recordingStatus), [recordingStatus]);
  useEffect(() => {
    getFullReport(sessionId).then(setFull).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [sessionId]);
  // A past session: use its saved recording if the parent chose to keep one.
  useEffect(() => {
    if (replayMedia) return;
    getSavedRecording(sessionId)
      .then((m) => {
        setSaved(m);
        if (m) setStatus("saved");
      })
      .catch(() => setSaved(null));
  }, [sessionId, replayMedia]);

  const remove = async () => {
    if (!window.confirm("Delete the saved camera recording for this session? This can't be undone.")) return;
    await deleteRecording(sessionId);
    setSaved(null);
    setStatus("deleted");
  };

  const savePdf = async () => {
    if (!body.current || !full) return;
    setPdfBusy(true);
    try {
      const date = new Date().toISOString().slice(0, 10);
      // Loaded on demand: the PDF libraries are large and most visits never export.
      const { downloadReportPdf } = await import("../pdf");
      await downloadReportPdf(body.current, {
        filename: `omli-${view}-report-${sessionId.slice(0, 8)}-${date}.pdf`,
        title: view === "parent" ? "Parent report" : "Clinician report",
        lines: [`Age ${full.age_months} months`, `Created ${date}`, `Session ${sessionId}`],
      });
    } catch (e) {
      window.alert(`Couldn't create the PDF: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPdfBusy(false);
    }
  };

  const media = replayMedia ?? saved;
  if (replay) return <Replay sessionId={sessionId} report={report} media={media} onClose={() => setReplay(false)} />;

  return (
    <div className="panel wide">
      <div className="tabs">
        <button className={view === "parent" ? "tab active" : "tab"} onClick={() => setView("parent")}>
          Parent report
        </button>
        <button className={view === "clinician" ? "tab active" : "tab"} onClick={() => setView("clinician")}>
          Clinician report
        </button>
        <button className="tab pdf-tab" onClick={() => void savePdf()} disabled={!full || pdfBusy}>
          {pdfBusy ? "Preparing PDF…" : "⤓ Download PDF"}
        </button>
        <button className="tab replay-tab" onClick={() => setReplay(true)}>
          ▶ Analysis replay
        </button>
      </div>
      {status && (
        <p className="recording-status small">
          {status === "saving" && "Saving the camera recording…"}
          {status === "saved" && (
            <>
              Camera recording saved with this session.{" "}
              <button className="link" onClick={() => void remove()}>Delete recording</button>
            </>
          )}
          {status === "deleted" && "Saved recording deleted."}
          {status.startsWith("failed") && `The recording couldn't be saved (${status.slice(8)}).`}
        </p>
      )}
      {error && <p className="error">Couldn't build the report: {error}</p>}
      {!full && !error && <p className="muted">Building the report…</p>}
      {full && (
        <div ref={body}>
          {view === "parent" ? <ParentView full={full} sessionId={sessionId} /> : <ClinicianView full={full} sessionId={sessionId} />}
        </div>
      )}
    </div>
  );
}

// --- parent ---------------------------------------------------------------------------------

function ParentView({ full, sessionId }: { full: FullReport; sessionId: string }) {
  const camera = full.camera.parent;
  return (
    <>
      <div className={`outcome ${ACTION_CLASS[full.action]}`}>
        <h1>{full.title}</h1>
        <p>{full.message}</p>
      </div>

      {full.red_flags.length > 0 && (
        <p className="banner">
          <b>Please mention these to a doctor soon:</b> {full.red_flags.join("; ")}.
        </p>
      )}
      {!full.has_questionnaire && (
        <p className="notice small">
          This report uses the camera session only.{" "}
          <a href={`?session=${encodeURIComponent(sessionId)}&questions=1`}>Answer a few questions</a> to complete it:
          they cover talking, understanding, play, movement and more.
        </p>
      )}

      <h2>What we found</h2>
      {full.conditions.length === 0 ? (
        <p>Nothing stood out from what we looked at.</p>
      ) : (
        full.conditions.map((c) => <ConditionCard key={c.key} c={c} autism={c.key === "ASD" ? full.autism_wheel : null} />)
      )}

      <h2>Development profile</h2>
      <p className="muted small">
        Each slice is one area of development. The bigger the slice, the more signs of difficulty were reported or seen in
        that area. Only the areas relevant to your child were asked about.
      </p>
      <DomainWheel slices={full.wheel} />

      {full.steps.length > 0 && (
        <>
          <h2>Next steps</h2>
          <ol>
            {full.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </>
      )}

      <h2>What the camera saw</h2>
      <ul className="findings">
        {camera.findings.map((f) => (
          <li key={f.title}>
            <b>{f.title}</b> {f.status && <span className={`pill ${f.status}`}>{STATUS_LABEL[f.status]}</span>}
            <div>{f.text}</div>
          </li>
        ))}
      </ul>

      <p className="disclaimer">
        This is a screening result, not a diagnosis. A developmental specialist confirms any diagnosis. Based on{" "}
        {full.questions_asked} answers and the camera session; Omli's screening engine is refined as more children are
        screened.
      </p>
    </>
  );
}

function ConditionCard({ c, autism }: { c: ConditionSection; autism: AutismWheelData | null }) {
  return (
    <section className={`condition ${BAND_CLASS[c.band]}`}>
      <h3>
        Signs linked to {c.short_name.toLowerCase().startsWith("late") ? "being a late talker" : c.short_name}{" "}
        <span className={`pill ${BAND_CLASS[c.band]}`}>{BAND_LABEL[c.band]}</span>
      </h3>
      <p>{c.about}</p>
      {c.for.length > 0 && (
        <ul className="evidence">
          {c.for.map((e) => (
            <li key={e.id}>
              <span className={`src ${e.source}`}>{e.source === "camera" ? "Camera" : "You told us"}</span> {e.text}
            </li>
          ))}
        </ul>
      )}
      {autism && <AutismWheel data={autism} />}
      <p className="small">
        <b>Who to see:</b> {c.refer}
      </p>
    </section>
  );
}

// The dataset's clinician notes name their reference (e.g. "DSM-5-TR: …", "(AAP 2019)"); the report doesn't.
const withoutRefs = (text: string) =>
  text.replace(/^DSM-5(-TR)?:\s*/, "").replace(/\s*\((?:AAP|CATALISE|JCIH|DSM)[^)]*\)/g, "");

/** Autism signs by the seven areas doctors assess, shown inside the autism section. */
function AutismWheel({ data, detailed = false }: { data: AutismWheelData; detailed?: boolean }) {
  const { social: a, repetitive: b } = data;
  return (
    <div className="autism-wheel">
      <h4>Autism wheel</h4>
      {detailed ? (
        <p className="small">
          Screening pattern only. A (social communication): {a.with_signs}/{a.total} criteria with signs, {a.checked}{" "}
          checked (a diagnosis requires all {a.dsm_needs}). B (restricted/repetitive): {b.with_signs}/{b.total} with signs,{" "}
          {b.checked} checked (requires at least {b.dsm_needs}). A criterion counts as "with signs" when at least half of
          its checked items were reported or seen.
        </p>
      ) : (
        <p className="small">
          Doctors look at seven areas when assessing autism: three about social communication (the first three slices) and
          four about repetitive behaviour and senses. Signs showed up in{" "}
          <b>
            {a.with_signs} of {a.total}
          </b>{" "}
          social areas and{" "}
          <b>
            {b.with_signs} of {b.total}
          </b>{" "}
          repetitive/sensory areas. An autism diagnosis usually needs differences in all {a.total} social areas and at least{" "}
          {b.dsm_needs} of the other {b.total}.
        </p>
      )}
      <DomainWheel slices={data.slices} detailed={detailed} label="Autism wheel" codesLabel="Area" />
    </div>
  );
}

// --- clinician -------------------------------------------------------------------------------

const pct = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`);

function ClinicianView({ full, sessionId }: { full: FullReport; sessionId: string }) {
  const cam = full.camera.clinician;
  const download = () => {
    const blob = new Blob([JSON.stringify(full, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `behavior-screening-${sessionId}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const shown = new Set(full.conditions.map((c) => c.key));

  return (
    <>
      <table className="kv">
        <tbody>
          <tr><th>Session</th><td>{sessionId}</td></tr>
          <tr><th>Age</th><td>{full.age_months} months</td></tr>
          <tr><th>Action</th><td>{full.action} · {full.title}</td></tr>
          <tr><th>Evidence</th><td>{full.observations.length} camera observations, {full.questions_asked} parent answers</td></tr>
          <tr><th>Hearing first</th><td>{full.hearing_test ? "yes" : "no"}</td></tr>
          {full.red_flags.length > 0 && <tr><th>Red flags</th><td>{full.red_flags.join("; ")}</td></tr>}
        </tbody>
      </table>

      <h2>All conditions</h2>
      <table className="grid">
        <thead>
          <tr><th>Condition</th><th>Prior</th><th>Posterior</th><th>Eligibility</th><th>Shown</th></tr>
        </thead>
        <tbody>
          {full.all_conditions.map((c) => (
            <tr key={c.key} className={shown.has(c.key) ? undefined : "muted"}>
              <td>{c.name}</td>
              <td>{pct(c.prior, 1)}</td>
              <td><b>{pct(c.probability, 1)}</b></td>
              <td>{c.eligibility}</td>
              <td>{shown.has(c.key) ? "yes" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Shown conditions: evidence</h2>
      {full.conditions.map((c) => (
        <section key={c.key} className="metric">
          <h3>
            {c.name} <span className={`pill ${BAND_CLASS[c.band]}`}>{c.band}</span> <span className="small">{pct(c.probability, 1)}</span>
          </h3>
          <p className="small muted">{withoutRefs(c.clinical_note)} · Diagnosable: {withoutRefs(c.dx_age)}</p>
          {c.key === "ASD" && <AutismWheel data={full.autism_wheel} detailed />}
          <table className="grid">
            <thead>
              <tr><th>Evidence</th><th>Source</th><th>Δ log-odds</th></tr>
            </thead>
            <tbody>
              {[...c.for, ...c.against].map((e) => (
                <tr key={e.id}>
                  <td className="wrap">{e.text}</td>
                  <td>{e.source}</td>
                  <td>{e.delta > 0 ? "+" : ""}{e.delta.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small"><b>Refer:</b> {c.refer}</p>
        </section>
      ))}

      <h2>Development profile</h2>
      <DomainWheel slices={full.wheel} detailed />

      {full.observations.length > 0 && (
        <>
          <h2>Camera observations used</h2>
          <table className="grid">
            <thead>
              <tr><th>Observation</th><th>Outcome</th><th>Confidence</th><th>Condition</th><th>LR</th></tr>
            </thead>
            <tbody>
              {full.observations.flatMap((o) =>
                o.terms.map((t) => (
                  <tr key={o.id + t.condition}>
                    <td className="wrap">{o.label ?? o.id}</td>
                    <td>{o.outcome}</td>
                    <td>{o.confidence}</td>
                    <td>{t.condition}</td>
                    <td>{t.lr}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </>
      )}

      {full.answers.length > 0 && (
        <>
          <h2>Parent answers ({full.answers.length})</h2>
          <table className="grid">
            <thead>
              <tr><th>#</th><th>Item</th><th>Domain</th><th>Answer</th></tr>
            </thead>
            <tbody>
              {full.answers.map((a, i) => (
                <tr key={a.question_id}>
                  <td>{i + 1}</td>
                  <td className="wrap">{a.clinical_name}</td>
                  <td>{a.domain}</td>
                  <td>{a.answer}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h2>Camera session details</h2>
      {cam.findings.map((f) => (
        <FindingBlock key={f.key} f={f} />
      ))}
      <h3>Calibration</h3>
      <table className="kv">
        <tbody>
          <tr><th>Quality</th><td>{cam.calibration.quality}{cam.calibration.reason && ` (${cam.calibration.reason})`}</td></tr>
          <tr><th>Side accuracy (validation)</th><td>{pct(cam.calibration.side_accuracy)}</td></tr>
          <tr><th>Mean |x error|</th><td>{pct(cam.calibration.mean_abs_err_x)} of width</td></tr>
          <tr><th>Fit points used</th><td>{cam.calibration.fit_points_used} / 5</td></tr>
          {cam.calibration.yaw_gain_source && (
            <tr>
              <th>Head-turn coefficient</th>
              <td>
                {cam.calibration.yaw_gain} screen widths/° ({cam.calibration.yaw_gain_source}; head moved{" "}
                {cam.calibration.yaw_spread_deg}° during calibration)
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <h3>Recording quality</h3>
      <table className="grid">
        <thead>
          <tr><th>Window</th><th>Face visible</th><th>Luma</th><th>Face width</th><th>Flags</th></tr>
        </thead>
        <tbody>
          {Object.entries(cam.quality).map(([name, q]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{pct(q.face_ratio)}</td>
              <td>{q.median_luma ?? "—"}</td>
              <td>{q.median_face_w ?? "—"}</td>
              <td>{q.flags.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Raw measurements</h3>
      {cam.metrics.map((m) => (
        <MetricBlock key={m.key} metric={m} />
      ))}

      <button className="link no-pdf" onClick={download}>Download full report (JSON)</button>
    </>
  );
}

function FindingBlock({ f }: { f: Finding }) {
  return (
    <section className="metric">
      <h3>
        {f.title}{" "}
        {f.status && <span className={`pill ${f.status}`}>{STATUS_LABEL[f.status]}</span>}
        {f.confidence && <span className="pill">{f.confidence} confidence</span>}
      </h3>
      <p>{f.measured}</p>
      {f.meaning && <p className="muted">{f.meaning}</p>}
    </section>
  );
}

function MetricBlock({ metric: m }: { metric: MetricResult }) {
  const columns = m.trials.length ? Object.keys(m.trials[0]).filter((k) => k !== "frames") : [];
  return (
    <section className="metric">
      <h3>
        {m.label} <span className={`pill ${m.status}`}>{STATUS_LABEL[m.status]}</span>
        {m.confidence && <span className="pill">{m.confidence} confidence</span>}
      </h3>
      <p>{m.summary}</p>
      {m.reasons.length > 0 && <p className="muted small">Notes: {m.reasons.join("; ")}</p>}
      {columns.length > 0 && (
        <table className="grid">
          <thead>
            <tr>{columns.map((k) => <th key={k}>{k}</th>)}</tr>
          </thead>
          <tbody>
            {m.trials.map((t, i) => (
              <tr key={i}>{columns.map((k) => <td key={k}>{formatCell(t[k])}</td>)}</tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}
