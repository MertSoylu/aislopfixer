"""Detect the security flaws AI code generators actually ship in 2026.

Large-scale audits of LLM output (Veracode, Endor Labs, the 2025 USENIX study,
arXiv:2510.26103) put the real risk not in marketing fluff but in *insecure
code*: roughly half of generated snippets carry a known weakness, XSS is missed
~86% of the time, and hardcoded credentials / secret leakage rose ~40%. This
rule targets the concrete, high-precision, offline-detectable shapes of those
flaws in web sources:

* **XSS sinks** (CWE-79/80) — ``innerHTML``/``outerHTML`` assigned a dynamic
  value, ``dangerouslySetInnerHTML``, Vue ``v-html``, ``document.write``,
  ``insertAdjacentHTML``.
* **Code injection** (CWE-94/95) — ``eval``, ``new Function``, string-bodied
  ``setTimeout``/``setInterval``.
* **SQL injection** (CWE-89) — a SQL keyword inside a template literal with
  ``${…}`` interpolation, or built by string concatenation.
* **Command injection** (CWE-78) — ``exec``/``execSync`` fed an interpolated or
  concatenated command.
* **Broken transport security** (CWE-295) — ``rejectUnauthorized: false``,
  ``strictSSL: false``, ``NODE_TLS_REJECT_UNAUTHORIZED=0``.
* **Over-permissive CORS** (CWE-942) — ``Access-Control-Allow-Origin: *`` /
  ``origin: '*' | true``.
* **Weak crypto / insecure randomness** (CWE-327/338) — MD5/SHA-1 hashing, the
  deprecated ``createCipher``, ``Math.random()`` used to mint a secret/token.
* **Hardcoded real secrets** (CWE-798) — provider key formats (AWS, GitHub,
  OpenAI, Stripe, Google, Slack), JWTs and PEM private-key blocks.

Everything is MANUAL: a vulnerability is resolved by judgement (sanitize,
parameterize, rotate-and-move-to-env), never by a blind text substitution.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from ..models import Category, Fixability, Severity, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule

_I = re.IGNORECASE

# A static single-string assignment (``el.innerHTML = "<b>hi</b>"``) is not the
# dynamic-injection smell we are after; anything with a variable, a ``${…}``
# template or ``+`` concatenation is.
_STATIC_STR = re.compile(r"""^(['"]).*\1\s*;?\s*$""", re.S)


def _rest_of_line(text: str, pos: int) -> str:
    nl = text.find("\n", pos)
    return text[pos: nl if nl != -1 else len(text)]


def _dynamic_rhs(m: re.Match, sf: SourceFile) -> bool:
    """True when the assignment's right-hand side is not a static string."""
    rest = _rest_of_line(sf.text, m.end()).strip()
    if not rest:
        return False
    if _STATIC_STR.match(rest) and "+" not in rest and "${" not in rest:
        return False
    return True


# Math.random() is only a vulnerability when its output is used as a secret /
# identity value; as jitter or a demo color it is fine. Gate on nearby intent.
_SECRET_CTX = re.compile(
    r"\b(?:token|secret|password|passwd|otp|nonce|salt|session|api[_-]?key|"
    r"key|uuid|guid|id|code|csrf|auth)\b",
    _I,
)


def _random_for_secret(m: re.Match, sf: SourceFile) -> bool:
    ls = sf.text.rfind("\n", 0, m.start()) + 1
    nl = sf.text.find("\n", m.end())
    line = sf.text[ls: nl if nl != -1 else len(sf.text)]
    return bool(_SECRET_CTX.search(line))


_SQL_KW = r"(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION|CREATE|ALTER)"
_SECRET_FIX = "Rotate this credential immediately and load it from the environment"


def _shannon(s: str) -> float:
    """Shannon entropy (bits/char) of a string — high for random credentials."""
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


# Values that merely *look* like secrets but are placeholders — those are the
# secrets.py rule's job, not this one. Keeps the entropy check from double-firing.
_PLACEHOLDERISH = re.compile(
    r"your|xxx|x{6,}|change[_\- ]?me|placeholder|example|dummy|sample|todo|tbd|"
    r"<[^>]*>|\.\.\.|insert|replace|123456|abcdef|secret|password",
    _I,
)


def _high_entropy_secret(m: re.Match, sf: SourceFile) -> bool:
    """True when a credential identifier is assigned a real-looking random literal."""
    val = m.group(2)
    if not val or len(val) < 20 or " " in val:
        return False
    if _PLACEHOLDERISH.search(val) or "process.env" in val or "import.meta" in val:
        return False
    classes = sum(bool(re.search(p, val)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]"))
    return classes >= 2 and _shannon(val) >= 3.5


@file_rule
class SecurityRule(PatternRule):
    category = Category.SECURITY
    patterns = [
        # ----------------------------------------------------------- XSS sinks
        Pattern(
            id="security.xss_innerhtml",
            regex=re.compile(r"\.(?:inner|outer)HTML\s*="),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="XSS sink: dynamic value assigned to innerHTML/outerHTML",
            suggested_fix="Use textContent, or sanitize the HTML (e.g. DOMPurify)",
            guard=_dynamic_rhs,
            exclude_strings=True,
            exclude_comments=True,
        ),
        Pattern(
            id="security.xss_dangerously_set",
            regex=re.compile(r"dangerouslySetInnerHTML"),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="React dangerouslySetInnerHTML — raw HTML injection (XSS)",
            suggested_fix="Render text, or sanitize with DOMPurify before injecting",
            exclude_comments=True,
        ),
        Pattern(
            id="security.xss_v_html",
            regex=re.compile(r"\bv-html\s*="),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Vue v-html renders unsanitized HTML (XSS)",
            suggested_fix="Use {{ }} interpolation or sanitize the HTML first",
            exclude_comments=True,
        ),
        Pattern(
            id="security.xss_document_write",
            regex=re.compile(r"\bdocument\.write(?:ln)?\s*\("),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="document.write — XSS-prone and blocks the parser",
            suggested_fix="Build DOM nodes with textContent instead",
            exclude_strings=True,
            exclude_comments=True,
        ),
        Pattern(
            id="security.xss_insert_adjacent",
            regex=re.compile(r"\.insertAdjacentHTML\s*\("),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="insertAdjacentHTML with untrusted input is an XSS sink",
            suggested_fix="Sanitize the HTML or use insertAdjacentText",
            exclude_strings=True,
            exclude_comments=True,
        ),
        # ------------------------------------------------------ code injection
        Pattern(
            id="security.eval",
            regex=re.compile(r"\beval\s*\("),
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="eval() executes arbitrary code (code injection)",
            suggested_fix="Remove eval; parse data with JSON.parse or a real API",
            exclude_strings=True,
            exclude_comments=True,
        ),
        Pattern(
            id="security.new_function",
            regex=re.compile(r"\bnew\s+Function\s*\("),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="new Function() compiles code at runtime (code injection)",
            suggested_fix="Replace with a concrete function; never build code from input",
            exclude_strings=True,
            exclude_comments=True,
        ),
        Pattern(
            id="security.string_timer",
            regex=re.compile(r"\bset(?:Timeout|Interval)\s*\(\s*['\"]"),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="setTimeout/setInterval with a string body is implicit eval",
            suggested_fix="Pass a function reference, not a code string",
            exclude_strings=True,
            exclude_comments=True,
        ),
        # -------------------------------------------------------- SQL injection
        # NB: these intentionally match *inside* a string/template literal, so
        # exclude_strings must stay off — only commented-out code is skipped.
        Pattern(
            id="security.sqli_template",
            regex=re.compile(r"`[^`]*\b" + _SQL_KW + r"\b[^`]*\$\{[^`]*`", _I | re.S),
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="SQL injection: query built with template-literal interpolation",
            suggested_fix="Use parameterized queries / prepared statements",
            exclude_comments=True,
        ),
        Pattern(
            id="security.sqli_concat",
            regex=re.compile(
                r"['\"][^'\"\n]*\b" + _SQL_KW + r"\b[^'\"\n]*['\"]\s*\+\s*\w",
                _I,
            ),
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="SQL injection: query built by string concatenation",
            suggested_fix="Use parameterized queries / prepared statements",
            exclude_comments=True,
        ),
        # ---------------------------------------------------- command injection
        Pattern(
            id="security.command_injection",
            regex=re.compile(
                r"\b(?:child_process\.)?exec(?:Sync)?\s*\(\s*"
                r"(?:`[^`]*\$\{|['\"][^'\"\n]*['\"]\s*\+|[A-Za-z_$][\w$]*\s*\+)",
            ),
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="Command injection: shell command built from dynamic input",
            suggested_fix="Use execFile/spawn with an argument array; never interpolate",
            exclude_strings=True,
            exclude_comments=True,
        ),
        # ------------------------------------------------- broken TLS / transport
        Pattern(
            id="security.tls_disabled",
            regex=re.compile(
                r"rejectUnauthorized\s*:\s*false"
                r"|strictSSL\s*:\s*false"
                r"|NODE_TLS_REJECT_UNAUTHORIZED\s*[:=]\s*['\"]?0['\"]?",
                _I,
            ),
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="TLS certificate validation disabled — enables MITM",
            suggested_fix="Remove this; fix the certificate chain instead",
            exclude_comments=True,
        ),
        # -------------------------------------------------------- permissive CORS
        Pattern(
            id="security.cors_wildcard",
            regex=re.compile(
                r"['\"]?Access-Control-Allow-Origin['\"]?\s*[:,]\s*['\"]\*['\"]"
                r"|\borigin\s*:\s*(?:['\"]\*['\"]|true\b)",
                _I,
            ),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Over-permissive CORS (origin '*'/true) exposes the API",
            suggested_fix="Allow an explicit list of trusted origins",
            exclude_comments=True,
        ),
        # ----------------------------------------------- weak crypto / randomness
        Pattern(
            id="security.weak_hash",
            regex=re.compile(r"createHash\s*\(\s*['\"](?:md5|sha1)['\"]", _I),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Weak hash (MD5/SHA-1) — broken for security use",
            suggested_fix="Use SHA-256+; for passwords use bcrypt/scrypt/argon2",
            exclude_strings=True,
            exclude_comments=True,
        ),
        Pattern(
            id="security.weak_cipher",
            regex=re.compile(r"\bcrypto\.createCipher\s*\("),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Deprecated createCipher (no IV) — insecure encryption",
            suggested_fix="Use createCipheriv with a random IV",
            exclude_strings=True,
            exclude_comments=True,
        ),
        Pattern(
            id="security.insecure_random",
            regex=re.compile(r"\bMath\.random\s*\(\s*\)"),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Math.random() is not cryptographically secure for secrets",
            suggested_fix="Use crypto.randomUUID() / crypto.getRandomValues()",
            guard=_random_for_secret,
            exclude_strings=True,
            exclude_comments=True,
        ),
        # ------------------------------------------------ client-side token storage
        # Storing a credential in local/sessionStorage makes it readable by any
        # XSS payload — a default move of generated auth examples.
        Pattern(
            id="security.token_in_storage",
            regex=re.compile(
                r"\b(?:local|session)Storage\s*\.\s*setItem\s*\(\s*(['\"`])[\w.:-]*"
                r"(?:[Tt]oken|TOKEN|[Jj][Ww][Tt]|[Ss]ecret|[Cc]redentials?|"
                r"[Pp]assw(?:or)?d|[Aa]pi[_-]?[Kk]ey|[Aa]uth(?=[_\-A-Z'\"`]))"
                r"[\w.:-]*\1"
            ),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Auth token stored in web storage — stealable by any XSS",
            suggested_fix="Keep tokens in an httpOnly cookie or in memory",
            exclude_strings=True,
            exclude_comments=True,
        ),
        # ------------------------------------------------- postMessage wildcard
        Pattern(
            id="security.postmessage_wildcard",
            regex=re.compile(r"\.postMessage\s*\([^)\n]*,\s*['\"]\*['\"]"),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="postMessage with targetOrigin '*' — data leaks to any window",
            suggested_fix="Pass the exact target origin instead of '*'",
            exclude_strings=True,
            exclude_comments=True,
        ),
        # --------------------------------------------------- hardcoded real secrets
        # No masking: a real key leaks whether it sits in a string or a comment.
        Pattern(
            id="security.hardcoded_secret",
            regex=re.compile(
                r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"                       # AWS access key
                r"|\bgh[pousr]_[A-Za-z0-9]{36}\b"                      # GitHub token
                r"|\bgithub_pat_[0-9A-Za-z_]{22,}\b"
                r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b"                # OpenAI key
                r"|\b(?:sk|rk)_live_[0-9a-zA-Z]{16,}\b"               # Stripe secret
                r"|\bAIza[0-9A-Za-z_\-]{35}\b"                         # Google API key
                r"|\bxox[baprs]-[0-9A-Za-z-]{10,}\b"                  # Slack token
                r"|\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}\b"  # JWT
                r"|-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",  # PEM key
            ),
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="Hardcoded secret (real key/token format) committed to source",
            suggested_fix=_SECRET_FIX,
        ),
        # Generic high-entropy credential the provider-prefix list above misses:
        # a secret-ish identifier assigned a long, random-looking literal.
        Pattern(
            id="security.high_entropy_secret",
            regex=re.compile(
                r"\b(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|"
                r"client[_-]?secret|auth[_-]?token|private[_-]?key|token|"
                r"password|passwd|pwd)\b\s*[:=]\s*(['\"])([^'\"\n]{20,})\1",
                _I,
            ),
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="Possible hardcoded secret (high-entropy literal in source)",
            suggested_fix=_SECRET_FIX,
            group=2,
            guard=_high_entropy_secret,
            exclude_comments=True,
        ),
    ]
