# Signal → Condition Mapping: Design (v0.2)

> **Goal:** turn what we measure (camera session, later the speech assessment) into a report that says *what was seen, what research links it to, how likely a condition is, and what to do next*, instead of raw numbers.
> **Scope:** Autism (ASD) and hearing now; speech & language next. ADHD, motor and others later.
> **Implemented in:** `backend/scoring/evidence.py` (evidence table) and `backend/scoring/report.py` (findings, likelihood, recommendations). Scoring v0.2.0.

---

## 1. Rule: proven evidence only

Every cut-off, likelihood ratio and recommendation must come from a published study or clinical guideline. Nothing is set by intuition.

| Tier | What it needs | What it does in the report |
|---|---|---|
| **A** | Published diagnostic accuracy (sensitivity / specificity) | Finding + **changes the likelihood** (via its LR) |
| **B** | Published group difference, no accuracy figures | Finding with citation; never changes the likelihood |
| **C** | No published evidence | Not used anywhere |

**How an LR is taken from a paper (same for every Tier A item):**

- If the paper's counts are available: the 95% CI bound closest to 1 (the most conservative claim the data supports).
- Otherwise: the more conservative of the published estimates.
- It applies **only inside the age range the study tested**. Outside it, the finding is still reported but not used in the likelihood, and the report says why.

**Prior:** ASD ~1 in 100 (INCLEN 2018, children aged 2–9 in India).

**Combining:** findings are multiplied as independent given the condition (naive Bayes). That's an assumption, written into every clinician report, and the main thing validation must check.

---

## 2. Pipeline

```
 Camera session ─► module metrics ─► status per module ─► findings (Tier A/B, cited)
 (browser, on-device)  (quality-gated)   flagged / not_flagged /        │
                                          insufficient                  ├─► likelihood (prior × Tier A LRs)
                                                                        ├─► outcome + recommendations (guidelines)
                                                                        └─► parent view + clinician view
```

- A module that couldn't be measured (`insufficient`) is never evidence; it makes the outcome `incomplete` unless something else was flagged.
- Speech assessment results will join as additional modules (§5) once their evidence passes the rule in §1.

---

## 3. Autism + hearing: current evidence (Tier A)

### 3.1 Interest in people vs. objects (split screen, GeoPref-style)

| Result | Cut-off | LR (ASD) | Derivation |
|---|---|---|---|
| Flagged | social < 31% (i.e. > 69% geometric) | **8.5** | Replication n=1,863: sensitivity 17%, specificity 98% (more conservative of two published estimates; original n=444 gives 10.5) |
| Not flagged | social ≥ 31% | **0.85** | 0.83 / 0.98 |

Studied ages: 12–48 months. No borderline band exists in the literature, so there is none here. Property worth keeping: when this flags it is usually right, but most autistic toddlers don't flag, so "not flagged" barely lowers the likelihood.

### 3.2 Response to name

| Result | Rule | LR (ASD) | Derivation |
|---|---|---|---|
| Flagged | turned on at most 1 of the calls | **1.82** | Campbell 2019 (n=104): turned on > 1 trial in 2/22 autistic vs 52/82 other toddlers. LR+ 2.48 (95% CI 1.82–3.40); conservative bound used |
| Not flagged | turned on 2+ calls | **0.54** | LR− 0.14 (95% CI 0.04–0.54); conservative bound used |

Studied ages: 16–31 months. Same method as ours (tablet camera, head turn).

### 3.3 Tier B findings (reported, not in the likelihood)

- **Speed of turning to name:** autistic toddlers who turned took 2.0 s vs 1.1 s on average (Campbell 2019).
- **Attention to the videos:** older autistic toddlers attended less overall (Campbell 2019; group difference, no cut-off).

### 3.4 Worked example (implemented and tested)

| Evidence | Odds × | Likelihood |
|---|---|---|
| Prior (India) | — | 1.0% |
| Split screen flagged | × 8.5 | 7.9% |
| Name response flagged (age 16–31 m) | × 1.82 | 13.5% |
| Both not flagged | × 0.85 × 0.54 | 0.46% |

---

## 4. Hearing

### 4.1 Rule: hearing evaluation when a child doesn't attend to language

AAP (Johnson & Myers 2007): children with language delay or inattention to language should have their hearing evaluated. So **any** flagged name response (at any age) adds "hearing test by an audiologist" to the recommendations, and is the outcome (`hearing_check`) when nothing autism-linked was flagged within its studied ages. Hearing and autism signs overlap, and audiology belongs before or alongside an autism evaluation.

### 4.2 Planned module: sound orientation

**Why:** not turning to a name has two different explanations: not orienting to *voices* (autism) or not *hearing* (hearing loss). A non-social sound separates them.

**What:** during the calm animation, a short non-social sound (rattle, bell, 1.5 s) plays from the **left or right speaker only**. We measure a head turn **towards that side** within 3 s. 3 trials, random sides.

| Name | Sound | Points to |
|---|---|---|
| ✗ | ✓ | Autism-related signs; hearing response OK |
| ✗ | ✗ | **Hearing check first** |
| ✓ | ✗ | Possible one-sided / partial hearing issue → audiology |
| ✓ | ✓ | — |

**Evidence status:** Tier C until we find published accuracy figures for this kind of test. Until then it's reported as an observation, not used in any likelihood.

**Honest limits:** laptop speakers at home can only catch **moderate-to-severe** hearing loss. Passing does NOT rule out mild or one-sided loss or glue ear, so the report says "turned to sounds", never "hearing is normal".

---

## 5. Speech & language (next): candidate observations from the speech assessment

The speech assessment (`omli-speech-assessment-backend`, report built in `services/speech_assessment_service.py:_build_report_from_kidsvoiceq`) already produces age-normed metrics. Two rules for using them:

- **Shyness isn't delay.** Composite scores are multiplied by a participation factor `0.25 + 0.75 × response_rate`, so a shy child looks "delayed". Use raw metrics and percentiles only, and only when `language_sample_adequate` is true and the response rate is OK; otherwise `insufficient`.
- **Proxies aren't measurements.** When Azure pronunciation scoring is unavailable, articulation falls back to an acoustic proxy. Proxy-based values are not used.

**Age gap:** the assessment runs in buckets 3–4, 5–6 and 7–8 years, so there is no speech observation for 24–35 months.

| Candidate | From | Clinical cut-off | Evidence status |
|---|---|---|---|
| Expressive language (MLU) | `metrics.age_norms.mlu_percentile` (Brown/Rice norms) | < 10th percentile | Needs published accuracy for this cut-off → Tier B/C until found. Hindi norms provisional |
| Receptive / expressive bands | `band_results`, `delay_risk_below_bucket_floor` | floor not passed | Tier C (our own task norms) |
| Speech sounds (PCC) | `phoneme_assessment.pcc`, Azure path only | age-based PCC norms | Needs PCC norm source per age before use |
| Fluency | disfluencies per 100 words | > 15 significant (Yairi & Ambrose) | English only; not used for `hi` / `mixed` |

Not mapped, on purpose: apraxia (CAS) needs inconsistency and oral-motor measures we don't have; voice measures (jitter, shimmer, HNR, pitch) have no evidence for developmental conditions and are noisy on laptop mics; automatic prosody for autism isn't validated.

Language delay alone is weak evidence for autism (most late talkers aren't autistic). The useful combinations are language delay **plus** camera autism signs, or language delay **plus** no sound orientation (→ hearing).

---

## 6. Report

### Parent view

1. **Headline** from the outcome rule (refer / hearing_check / incomplete / no_signs).
2. **What we saw:** one line per module with the measured fact and a "Sign seen / Not seen / Not measured" tag.
3. **What it means:** "Among children with the same results, about N in 100 are autistic, compared with about 1 in 100 children in India overall." (Shown only when a Tier A finding falls within its studied ages.)
4. **Next steps** from guidelines.
5. **Not checked in this session:** hearing, speech & language, pointing / pretend play / repetitive behaviours, motor, ADHD.

### Clinician view

- Each finding with tier, status, confidence, the published meaning, age-range note and citations.
- Likelihood table: prior, each LR with its derivation, excluded findings with the reason, the independence assumption.
- Recommendations with their guideline sources.
- What wasn't assessed and how to assess it.
- Calibration, recording quality, raw per-trial measurements, scoring version, stimulus set.

### Outcome rule (guidelines, in priority order)

| Outcome | When | Source |
|---|---|---|
| `refer` | an autism-linked finding met its published cut-off within its studied ages | AAP 2020 (refer on positive screen; start early intervention without waiting) |
| `hearing_check` | turned to name at most once | AAP 2007 |
| `incomplete` | nothing flagged, a module unmeasured | — |
| `no_signs` | everything measured, nothing flagged | AAP 2020: routine autism screening at 18 and 24 months still recommended |

---

## 7. What's proven and what's assumed

| Item | Status |
|---|---|
| Split-screen cut-off and LRs | Published (GeoPref), but with their stimuli and an eye-tracker; ours are Pexels clips and a webcam |
| Name-response rule and LRs | Published (Campbell 2019), same method, small sample (22 autistic children) |
| Prior | Published Indian population rate (2–9 years; no separate under-2 figure) |
| Combining findings | Naive Bayes assumption |
| Thresholds on Indian children | **Not validated yet**: every clinician report says so |

---

## 8. Validation plan (needed before any accuracy claim)

1. **Clinical partner:** developmental paediatrician / child psychologist running ADOS-2, plus audiology.
2. **Sample:** children referred for developmental concerns + typical controls, 18–60 months. For sensitivity/specificity ±10% per condition: ~100 children with the condition and ~100 without.
3. **Procedure:** camera session (+ speech assessment where age allows), blinded to the clinician's assessment.
4. **Outputs:** LRs re-estimated on our own data (replacing the published ones), cut-offs checked, sensitivity/specificity/PPV/NPV per age band, and a check of the independence assumption.
5. **Re-score** all stored sessions with the new evidence table (`uv run python -m app.rescore`).

---

## 9. Build steps

| # | Step | Status |
|---|---|---|
| 1 | Evidence table (tiers, LRs, sources, age ranges) + clinical report | ✅ done (v0.2.0) |
| 2 | Tier B metrics from data we already record: head movement, smile to social moments, blink rate | to do, once a published source per metric is confirmed |
| 3 | Sound orientation module | to do (§4.2) |
| 4 | Gaze-following (joint attention) module | to do |
| 5 | Speech assessment → findings adapter | to do (§5), evidence check first |
| 6 | Validation study | with clinical partner |

---

## Sources

- Pierce et al. 2016, *Biol Psychiatry* (GeoPref, n=444); replication n=1,863: [PMC8917231](https://pmc.ncbi.nlm.nih.gov/articles/PMC8917231); [UCSD summary](https://neurosciences.ucsd.edu/centers-programs/autism/early/eye-gaze-biomarkers.html)
- Campbell et al. 2019, *Autism* 23(3): computer-vision response to name: [SAGE](https://journals.sagepub.com/doi/full/10.1177/1362361318766247)
- Nadig et al. 2007 (response to name at 12 m): [ADC summary](https://adc.bmj.com/content/92/8/730)
- Miller et al. 2017, *J Pediatr* (response to name, infant siblings): [PMC5370582](https://pmc.ncbi.nlm.nih.gov/articles/PMC5370582/)
- Arora et al. 2018, *PLoS Med* (INCLEN, neurodevelopmental disorders in India): [PMC5655917](https://pmc.ncbi.nlm.nih.gov/articles/PMC5655917)
- Hyman et al. 2020, *Pediatrics* (AAP autism guideline): [summary](https://apps.asha.org/EvidenceMaps/Articles/ArticleSummary/456cadf5-b603-4b03-ae14-3fb63daf5f59)
- Johnson & Myers 2007, *Pediatrics* (AAP; hearing evaluation): [summary](https://apps.asha.org/EvidenceMaps/Articles/ArticleSummary/68f50eb3-29e6-4a8d-85f0-f7d0cf0c7b51)
- Perochon et al. 2023, *Nature Medicine* (SenseToKnow): [Duke](https://pratt.duke.edu/news/autism-app-2023/)
- Canvas Dx FDA 510(k) K243558: [summary](https://fda.innolitics.com/device/K243558); payer review: [BCBS RI](https://www.bcbsri.com/providers/medicalpolicies/files/digital-health-technologies-diagnostic-applications)
- Hearing loss / autism overlap: [ASHA 2019](https://pubs.asha.org/doi/10.1044/2019_AJA-19-0047), [CU Boulder](https://www.colorado.edu/slhs/2021/03/26/co-occurrence-hearing-loss-and-autism-spectrum-disorders)
