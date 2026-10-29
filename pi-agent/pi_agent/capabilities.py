"""Product capabilities selected at the entry, independent of serialization."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    user_input: bool = False
    structured_answers: bool = False
    skill_groups: tuple[str, ...] = ("common",)


INTERACTIVE = RuntimeCapabilities(True, True, ("common", "agui"))
STANDARD = RuntimeCapabilities()
