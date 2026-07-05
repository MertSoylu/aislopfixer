"""Detect placeholder / hardcoded secrets — a runtime-breaking AI mistake.

Generated code routinely leaves credentials as obvious placeholders::

    const apiKey = "YOUR_API_KEY_HERE";
    OPENAI_KEY = "sk-xxxxxxxxxxxxxxxxxxxx"
    password: "changeme"
    token = "<your-token>"

This is two mistakes at once: the app fails at runtime because the value is fake,
and it normalizes hardcoding secrets in source. We flag the placeholder, never a
value that looks like a *real* secret (those are caught by a different class of
tool), and never the correct pattern — reading from the environment
(``process.env.API_KEY``) carries no literal placeholder and is left alone.

Three shapes:

* **placeholder tokens** — ``YOUR_API_KEY``, ``your-token``, ``api_key_here``,
  ``<your-secret>``. Word parts joined by ``_``/``-`` (or angle-bracketed), so
  prose like "Change Password" is not matched.
* **provider stub keys** — an ``sk-`` / ``pk_`` prefix followed by ``xxxx`` /
  ``...`` / ``your`` rather than a real body.
* **credential assignments** — a ``key|secret|token|password|…`` identifier
  assigned a quoted placeholder value (``"changeme"``, ``"<...>"``, ``"xxxx…"``).
"""

from __future__ import annotations

import re

from ..models import Category, Fixability, Severity
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule

_I = re.IGNORECASE

_FIX = "Load the secret from an environment variable; never hardcode it"

# ---- placeholder tokens (verb_noun joined by _/-, or angle-bracketed) --------
_NOUN = (
    r"(?:api[_\-]?key|secret(?:[_\-]?key)?|access[_\-]?token|client[_\-]?secret|"
    r"auth[_\-]?token|private[_\-]?key|token|password|passwd|credentials?|key)"
)
_PLACEHOLDER_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"(?:your|insert|replace|add|change|my)[_\-](?:own[_\-])?" + _NOUN + r"(?:[_\-]here)?"
    r"|" + _NOUN + r"[_\-](?:goes[_\-])?here"
    r"|<(?:your[_\- ]?)?" + _NOUN + r">"
    r")(?![A-Za-z0-9_])",
    _I,
)

# ---- provider stub keys (real prefix, placeholder body) ----------------------
_FAKE_KEY = re.compile(
    r"\b(?:sk|pk|rk)[-_](?:live|test|proj)?[-_]?"
    r"(?:x{6,}|X{6,}|\.{3,}|your[_\w-]*|placeholder|xxxx[\w-]*|0{6,}|1234567890[\w-]*)",
)

# ---- credential identifier assigned a quoted placeholder value ---------------
_PLACEHOLDER_VALUE = (
    r"(?:your[_\- ]?[\w-]*|own[_\- ]?[\w-]*|change[_\- ]?me|changeme|replace[_\- ]?me|"
    r"placeholder|todo|tbd|n/?a|xxx+|x{8,}|insert[_\- ]?[\w-]*|add[_\- ]?[\w-]*|"
    r"<[^\">]{1,40}>|secret|password|passw0rd|123456|12345678|admin|example|dummy|"
    r"sample|test[_\-]?key|foo|bar|baz)"
)
_ASSIGN = re.compile(
    r"\b(?:api[_\-]?key|api[_\-]?secret|secret(?:[_\-]?key)?|access[_\-]?token|"
    r"client[_\-]?secret|auth[_\-]?token|private[_\-]?key|token|password|passwd|pwd)\b"
    r"\s*[:=]\s*(['\"])\s*(" + _PLACEHOLDER_VALUE + r")\s*\1",
    _I,
)


@file_rule
class SecretPlaceholderRule(PatternRule):
    category = Category.PLACEHOLDER
    patterns = [
        Pattern(
            id="secret.placeholder_token",
            regex=_PLACEHOLDER_TOKEN,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Placeholder credential left in source",
            suggested_fix=_FIX,
        ),
        Pattern(
            id="secret.fake_key",
            regex=_FAKE_KEY,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Placeholder API key — provider prefix with a fake body",
            suggested_fix=_FIX,
        ),
        Pattern(
            id="secret.assignment",
            regex=_ASSIGN,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Credential assigned a placeholder value",
            suggested_fix=_FIX,
            group=2,
        ),
    ]
