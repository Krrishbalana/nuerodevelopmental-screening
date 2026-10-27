"""Saathi adaptive screening engine, vendored into this backend so one server runs everything.

Copied on 2026-10-26 from `nuerologically disorder finder/backend`:
  app/domain/   -> saathi/domain/   (minus media.py, which only the media upload service used)
  app/engine/   -> saathi/engine/   (unchanged apart from import paths)
  app/services/dataset_service.py -> saathi/dataset_service.py
  data/adaptive-screening-dataset.json -> backend/data/saathi/ (sha256 47a91043b519b908…)
  Local change: ASD base_rate 0.03 (US, CDC) -> 0.01 (India, INCLEN 2018); sha256 now 2ee3e002484377c9…; Typical baby 9 m regression profile now stops at 21 questions (lower prior)
The engine is pure (no I/O): the session store lives in app/questionnaire.py.
Its likelihood ratios are estimated (lr_source "estimated_from_strength"); they are used in reports
and will be re-estimated from collected outcomes over time.
"""
