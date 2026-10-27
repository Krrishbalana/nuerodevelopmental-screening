"""Every piece of published evidence the report is allowed to use. Nothing else.

Tiers
  A  Published diagnostic accuracy (sensitivity/specificity) → likelihood ratios.
     Only Tier A changes the estimated likelihood of a condition.
  B  Published group difference (e.g. "autistic toddlers turned later"), no accuracy figures.
     Shown as a finding with its citation; never changes the likelihood.
  C  No published evidence → not used anywhere.

LR derivation rule (applied the same way to every Tier A item):
  - If the paper's counts are available, use the 95% CI bound closest to 1 (the most
    conservative claim the data supports).
  - Otherwise use the more conservative of the published estimates.
  - An LR only applies inside the age range the study tested.

Combining items assumes they are independent given the condition (naive Bayes). That is an
assumption, stated in every clinician report, and the main thing validation must check.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    key: str
    citation: str
    url: str


SOURCES = {
    s.key: s
    for s in [
        Source(
            "inclen2018",
            "Arora NK et al. Neurodevelopmental disorders in children aged 2-9 years: population-based "
            "burden estimates across five regions in India. PLoS Med 2018;15(7):e1002615.",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC5655917",
        ),
        Source(
            "pierce2016",
            "Pierce K et al. Eye tracking reveals abnormal visual preference for geometric images as an "
            "early biomarker of an autism spectrum disorder subtype associated with increased symptom "
            "severity. Biol Psychiatry 2016;79(8):657-666 (n=444).",
            "https://neurosciences.ucsd.edu/centers-programs/autism/early/eye-gaze-biomarkers.html",
        ),
        Source(
            "wen2022",
            "GeoPref test replication in 1,863 toddlers: 69% geometric cut-off, sensitivity 17%, "
            "specificity 98%, PPV 81%.",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC8917231",
        ),
        Source(
            "campbell2019",
            "Campbell K et al. Computer vision analysis captures atypical attention in toddlers with "
            "autism. Autism 2019;23(3):619-628 (n=104, 16-31 months).",
            "https://journals.sagepub.com/doi/full/10.1177/1362361318766247",
        ),
        Source(
            "aap2020",
            "Hyman SL, Levy SE, Myers SM; AAP Council on Children with Disabilities. Identification, "
            "evaluation, and management of children with autism spectrum disorder. Pediatrics "
            "2020;145(1):e20193447.",
            "https://apps.asha.org/EvidenceMaps/Articles/ArticleSummary/456cadf5-b603-4b03-ae14-3fb63daf5f59",
        ),
        Source(
            "aap2007",
            "Johnson CP, Myers SM; AAP. Identification and evaluation of children with autism spectrum "
            "disorders. Pediatrics 2007;120(5):1183-1215: children with language delay or inattention to "
            "language should have their hearing evaluated.",
            "https://apps.asha.org/EvidenceMaps/Articles/ArticleSummary/68f50eb3-29e6-4a8d-85f0-f7d0cf0c7b51",
        ),
    ]
}


@dataclass(frozen=True)
class Prior:
    condition: str
    probability: float
    source: str
    note: str


ASD_PRIOR = Prior(
    condition="ASD",
    probability=0.01,
    source="inclen2018",
    note="About 1 in 100 children aged 2-9 in India (population study, five regions). "
    "No separate figure for under-2s was published.",
)


@dataclass(frozen=True)
class TierA:
    key: str  # matches the metric key
    condition: str
    flagged_means: str
    lr_flagged: float
    lr_not_flagged: float
    age_months: tuple[int, int]  # ages the studies tested; outside this the LR is not applied
    sources: tuple[str, ...]
    derivation: str


TIER_A = {
    e.key: e
    for e in [
        TierA(
            key="social_preference",
            condition="ASD",
            flagged_means="looked at geometric images more than 69% of the time (social < 31%)",
            lr_flagged=8.5,
            lr_not_flagged=0.85,
            age_months=(12, 48),
            sources=("wen2022", "pierce2016"),
            derivation="Sensitivity 17%, specificity 98% (replication, n=1,863; the more conservative of "
            "the two published estimates). LR+ = 0.17/0.02 = 8.5, LR- = 0.83/0.98 = 0.85.",
        ),
        TierA(
            key="name_response",
            condition="ASD",
            flagged_means="turned to their name on at most 1 trial",
            lr_flagged=1.82,
            lr_not_flagged=0.54,
            age_months=(16, 31),
            sources=("campbell2019",),
            derivation="Turned on more than one trial: 2/22 autistic vs 52/82 comparison toddlers. "
            "LR+ 2.48 (95% CI 1.82-3.40), LR- 0.14 (95% CI 0.04-0.54); conservative CI bounds used.",
        ),
    ]
}


@dataclass(frozen=True)
class TierB:
    key: str
    finding: str
    sources: tuple[str, ...]


TIER_B = {
    "name_latency": TierB(
        key="name_latency",
        finding="Autistic toddlers who do turn to their name take longer on average (about 2.0 s vs 1.1 s "
        "for other toddlers).",
        sources=("campbell2019",),
    ),
    "attention": TierB(
        key="attention",
        finding="Older autistic toddlers tend to pay less overall attention to videos like these. There is "
        "no cut-off, so this is shown for context only.",
        sources=("campbell2019",),
    ),
}


def cite(keys: tuple[str, ...] | list[str]) -> list[dict]:
    return [{"key": k, "citation": SOURCES[k].citation, "url": SOURCES[k].url} for k in keys]
