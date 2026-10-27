"""Enumerations shared across the domain and engine layers.

Values mirror the vocabulary used in adaptive-screening-engine-design.md
and the keys that appear literally in adaptive-screening-dataset.json.
"""

from enum import IntEnum, StrEnum


class AnswerKey(StrEnum):
    YES = "y"
    PROBABLY = "py"
    DONT_KNOW = "dk"
    PROBABLY_NOT = "pn"
    NO = "n"


class Direction(IntEnum):
    ABSENT = -1
    UNKNOWN = 0
    PRESENT = 1


class Eligibility(StrEnum):
    OK = "ok"
    WATCH = "watch"
    HIDDEN = "hidden"
    PAST = "past"


class Situation(StrEnum):
    HISTORY_ITEM = "history_item"
    WELL_PAST_RED_FLAG = "well_past_red_flag"
    PAST_RED_FLAG = "past_red_flag"
    UNUSUAL_BEHAVIOR = "unusual_behavior"
    PAST_TYPICAL = "past_typical"
    BEFORE_TYPICAL = "before_typical"


class Band(StrEnum):
    STRONG = "strong"
    LIKELY = "likely"
    POSSIBLE = "possible"
    UNLIKELY = "unlikely"


class Action(StrEnum):
    URGENT = "urgent"
    REFER = "refer"
    WATCH = "watch"
    ON_TRACK = "on_track"


class StepType(StrEnum):
    QUESTION = "question"
    URGENT = "urgent"
    PATTERN = "pattern"
    DONE = "done"


class QuestionType(StrEnum):
    HISTORY = "history"
    MILESTONE = "milestone"
    UNUSUAL_BEHAVIOR = "unusual_behavior"


class RuleId(StrEnum):
    URGENT_RED_FLAG = "urgent_red_flag"
    MAJOR_MILESTONE_MISSED = "major_milestone_missed"
    HEARING_FIRST = "hearing_first"
    AGE_GATES = "age_gates"
    SPCD_REQUIRES_NO_RRB = "spcd_requires_no_rrb"
    LATE_TALKER_REQUIRES_TYPICAL_SOCIAL = "late_talker_requires_typical_social"
    LATE_TALKER_TO_DLD = "late_talker_to_dld"
    NO_DIAGNOSIS_LANGUAGE = "no_diagnosis_language"
    RECHECK_ALWAYS = "recheck_always"


class MediaType(StrEnum):
    AUDIO = "audio"
    VIDEO = "video"
    EITHER = "either"


class CaptureMethod(StrEnum):
    RECORDED = "recorded"
    UPLOADED = "uploaded"


class Sex(StrEnum):
    BOY = "boy"
    GIRL = "girl"
    NA = "na"  # unspecified: no sex_boy/sex_girl odds multiplier is applied


class Born(StrEnum):
    TERM = "term"
    WEEKS_32_36 = "32_36"
    LT32 = "lt32"
