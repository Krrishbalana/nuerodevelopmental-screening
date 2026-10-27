"""Recording conditions for a time window: is the child visible, lit, at a sensible distance?"""

from statistics import median

from pydantic import BaseModel

from . import config as C
from .models import BrightnessSample, Frame
from .timeline import Timeline


class WindowQuality(BaseModel):
    frames: int
    face_ratio: float
    median_luma: float | None
    median_face_w: float | None
    flags: list[str]

    @property
    def ok(self) -> bool:
        return not self.flags


def window_quality(
    frames: Timeline[Frame],
    brightness: Timeline[BrightnessSample],
    start: float,
    end: float,
) -> WindowQuality:
    window = frames.between(start, end)
    with_face = [f for f in window if f.face]
    face_ratio = len(with_face) / len(window) if window else 0.0
    lumas = [b.luma for b in brightness.between(start, end)]
    widths = [f.face_w for f in with_face if f.face_w is not None]
    median_luma = median(lumas) if lumas else None
    median_face_w = median(widths) if widths else None

    flags: list[str] = []
    if not window:
        flags.append("no_frames")
    elif face_ratio < C.FACE_RATIO_MIN:
        flags.append("face_often_missing")
    if median_luma is not None and median_luma < C.LUMA_MIN:
        flags.append("too_dark")
    if median_face_w is not None and median_face_w < C.FACE_W_MIN:
        flags.append("too_far")
    if median_face_w is not None and median_face_w > C.FACE_W_MAX:
        flags.append("too_close")

    return WindowQuality(
        frames=len(window),
        face_ratio=round(face_ratio, 3),
        median_luma=None if median_luma is None else round(median_luma, 1),
        median_face_w=None if median_face_w is None else round(median_face_w, 3),
        flags=flags,
    )
