"""What a class expression actually resolves to.

``className={…}`` is where a real React project keeps its design decisions, and
reading it as "every string literal inside the braces" is both too generous and
too mean. Too generous, because a condition's operand — the ``"muted"`` in
``tone === "muted"`` — is not a class. Too mean, because a template literal's
static half is dropped the moment an interpolation appears, and that static
half is usually the band padding: the single most measured value in the tool.

So this module *evaluates* the expression instead of scraping it. With no
bindings it returns the **union** of every branch, which is the honest reading
of code whose inputs are unknown. Given ``env`` — the props a component was
actually called with — a decidable condition collapses to the branch that
renders, which is how :mod:`.render` tells one ``<Section tone="muted">`` from
the next.

Two rules keep it from inventing values:

* A token that touches an interpolation is **not** emitted. ``` `py-${n}` ```
  yields nothing; a partial token is not a class, and completing it would put a
  value nobody wrote into the vocabulary.
* Anything the evaluator cannot read falls back to the old literal scrape,
  never to a guess.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
_CALL = re.compile(r"([A-Za-z_$][\w$.]*)\s*\(")
_MAX_DEPTH = 12

# Placeholder standing in for an interpolation while a template literal is
# split into tokens. Chosen from a range that cannot occur in source class text.
_HOLE = "\x00"

#: Returned by :func:`_value` for ``undefined``/``null`` — a *known* absence,
#: which compares unequal to every string and is falsy. Distinct from ``None``,
#: which means "could not be read" and keeps a condition undecidable.
_UNDEF = object()


# ------------------------------------------------------------------ scanning
def skip_string(src: str, i: int) -> int:
    """Index just past the string literal opening at ``i``.

    Template literals are followed through their ``${…}`` holes, which may
    themselves contain strings and further templates.
    """
    quote = src[i]
    j, n = i + 1, len(src)
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if quote == "`" and c == "$" and src[j + 1:j + 2] == "{":
            j = skip_group(src, j + 1)
            continue
        if c == quote:
            return j + 1
        j += 1
    return n


_CLOSER = {"{": "}", "(": ")", "[": "]"}


def skip_group(src: str, i: int) -> int:
    """Index just past the bracket matching the one at ``i``."""
    opener = src[i]
    closer = _CLOSER.get(opener)
    if closer is None:
        return i + 1
    depth = 0
    j, n = i, len(src)
    while j < n:
        c = src[j]
        if c in "\"'`":
            j = skip_string(src, j)
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _top_positions(src: str):
    """Yield ``(index, char)`` for every character at nesting depth zero."""
    j, n = 0, len(src)
    while j < n:
        c = src[j]
        if c in "\"'`":
            j = skip_string(src, j)
            continue
        if c in "([{":
            j = skip_group(src, j)
            continue
        yield j, c
        j += 1


def _find_top(src: str, op: str) -> int:
    """Offset of ``op`` at nesting depth zero, or ``-1``."""
    for i, c in _top_positions(src):
        if c == op[0] and src[i:i + len(op)] == op:
            return i
    return -1


def _split_top(src: str, sep: str = ",") -> list[str]:
    """Split on a depth-zero separator, keeping empty pieces out."""
    out: list[str] = []
    last = 0
    for i, c in _top_positions(src):
        if c == sep:
            out.append(src[last:i])
            last = i + 1
    out.append(src[last:])
    return [p for p in out if p.strip()]


def _wraps(src: str, opener: str) -> bool:
    """True when ``src`` is one bracket group spanning the whole string."""
    return src.startswith(opener) and skip_group(src, 0) == len(src)


def _is_string(src: str) -> bool:
    return src[:1] in ("\"", "'") and skip_string(src, 0) == len(src)


_ESCAPES = {"\\": "\\", "'": "'", '"': '"', "n": " ", "t": " "}


def _unescape(s: str) -> str:
    if "\\" not in s:
        return s
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == "\\" and i + 1 < n:
            out.append(_ESCAPES.get(s[i + 1], s[i + 1]))
            i += 2
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _tokens(text: str) -> list[str]:
    return [t for t in _WS.split(text.strip()) if t]


# ---------------------------------------------------------------- conditions
def _value(src: str, env: dict[str, str], depth: int = 0):
    """Resolve ``src`` to a constant, ``_UNDEF``, or ``None`` when unreadable."""
    src = src.strip()
    if not src or depth > _MAX_DEPTH:
        return None
    while _wraps(src, "("):
        src = src[1:-1].strip()
    if _is_string(src):
        return _unescape(src[1:-1])
    if src in ("undefined", "null"):
        return _UNDEF
    if src.isdigit():
        return src
    if _IDENT.fullmatch(src) and src in env:
        return _value(env[src], env, depth + 1)
    return None


_COMPARISONS = ("===", "!==", "==", "!=")


def _truth(src: str, env: dict[str, str], depth: int = 0) -> bool | None:
    """Is this condition true, false, or unreadable (``None``)?"""
    src = src.strip()
    if not src or depth > _MAX_DEPTH:
        return None
    while _wraps(src, "("):
        src = src[1:-1].strip()
    if src.startswith("!") and not src.startswith("!="):
        inner = _truth(src[1:], env, depth + 1)
        return None if inner is None else not inner
    if src == "true":
        return True
    if src in ("false", "undefined", "null"):
        return False
    for op in _COMPARISONS:
        k = _find_top(src, op)
        if k < 0:
            continue
        # `===` also contains `==`; the longer operator is tried first, so a
        # shorter match here is genuine.
        left = _value(src[:k], env, depth + 1)
        right = _value(src[k + len(op):], env, depth + 1)
        if left is None or right is None:
            return None
        equal = left is right if _UNDEF in (left, right) else left == right
        return equal if op[0] == "=" else not equal
    if _IDENT.fullmatch(src) and src in env:
        # Resolve through the binding as a *condition*, not as a value: a prop
        # bound to `true` is a boolean, and reading it as the string "true"
        # left every bare `<Section muted>` undecided.
        return _truth(env[src], env, depth + 1)
    resolved = _value(src, env, depth + 1)
    if resolved is None:
        return None
    if resolved is _UNDEF:
        return False
    return bool(resolved)


# ---------------------------------------------------------------- evaluation
def _template(src: str, env: dict[str, str], depth: int) -> list[str]:
    """Tokens of a template literal, dropping any that touch an interpolation.

    The static text is reassembled with each hole replaced by a marker that
    contains no whitespace, then split: a token that *is* a marker contributes
    the hole's own classes, a token that merely *contains* one was glued to an
    interpolation and is discarded.
    """
    body = src[1:-1]
    holes: list[list[str]] = []
    parts: list[str] = []
    i, n = 0, len(body)
    last = 0
    while i < n:
        if body[i] == "\\":
            i += 2
            continue
        if body[i] == "$" and body[i + 1:i + 2] == "{":
            end = skip_group(body, i + 1)
            parts.append(_unescape(body[last:i]))
            parts.append(f"{_HOLE}{len(holes)}{_HOLE}")
            holes.append(_eval(body[i + 2:max(i + 2, end - 1)], env, depth + 1))
            i = last = end
            continue
        i += 1
    parts.append(_unescape(body[last:]))

    out: list[str] = []
    for token in _tokens("".join(parts)):
        if _HOLE not in token:
            out.append(token)
            continue
        if token.startswith(_HOLE) and token.endswith(_HOLE) and token.count(_HOLE) == 2:
            out.extend(holes[int(token[1:-1])])
    return out


def _is_object(inner: str) -> bool:
    """True for ``{ active: isOn }`` — clsx and Vue's object class syntax."""
    return _find_top(inner, ":") >= 0 and _find_top(inner, "?") < 0


def _object_keys(inner: str, env: dict[str, str], depth: int) -> list[str]:
    out: list[str] = []
    for pair in _split_top(inner, ","):
        k = _find_top(pair, ":")
        if k < 0:
            continue
        key, cond = pair[:k].strip(), pair[k + 1:]
        if _truth(cond, env, depth + 1) is False:
            continue
        if _is_string(key):
            out.extend(_tokens(_unescape(key[1:-1])))
        elif _IDENT.fullmatch(key):
            out.append(key)
    return out


def _ternary_colon(src: str, start: int) -> int:
    """Offset of the ``:`` belonging to the ``?`` before ``start``."""
    pending = 0
    for i, c in _top_positions(src):
        if i < start:
            continue
        if c == "?" and src[i:i + 2] not in ("?.", "??"):
            pending += 1
        elif c == ":" and src[i:i + 2] != "::":
            if pending == 0:
                return i
            pending -= 1
    return -1


def _harvest(src: str) -> list[str]:
    """Last resort: every string literal's tokens, template statics included."""
    out: list[str] = []
    j, n = 0, len(src)
    while j < n:
        c = src[j]
        if c in "\"'`":
            end = skip_string(src, j)
            body = src[j:end]
            if c == "`":
                out.extend(_template(body, {}, _MAX_DEPTH - 1))
            else:
                out.extend(_tokens(_unescape(body[1:-1])))
            j = end
            continue
        j += 1
    return out


def _eval(src: str, env: dict[str, str], depth: int = 0) -> list[str]:
    src = src.strip()
    if not src or depth > _MAX_DEPTH:
        return []
    while _wraps(src, "("):
        src = src[1:-1].strip()
        if not src:
            return []

    if _wraps(src, "{"):
        inner = src[1:-1]
        return (_object_keys(inner, env, depth) if _is_object(inner)
                else _eval(inner, env, depth + 1))
    if _wraps(src, "["):
        return [t for part in _split_top(src[1:-1], ",")
                for t in _eval(part, env, depth + 1)]
    if _is_string(src):
        return _tokens(_unescape(src[1:-1]))
    if src[0] == "`" and skip_string(src, 0) == len(src):
        return _template(src, env, depth)

    q = _find_top(src, "?")
    if q >= 0 and src[q:q + 2] not in ("?.", "??"):
        colon = _ternary_colon(src, q + 1)
        if colon > q:
            verdict = _truth(src[:q], env, depth + 1)
            if verdict is True:
                return _eval(src[q + 1:colon], env, depth + 1)
            if verdict is False:
                return _eval(src[colon + 1:], env, depth + 1)
            return (_eval(src[q + 1:colon], env, depth + 1)
                    + _eval(src[colon + 1:], env, depth + 1))

    for op in ("||", "??", "&&"):
        k = _find_top(src, op)
        if k < 0:
            continue
        left, right = src[:k], src[k + len(op):]
        verdict = _truth(left, env, depth + 1)
        if op == "&&":
            if verdict is False:
                return []
            return _eval(right, env, depth + 1)
        if verdict is True:
            return _eval(left, env, depth + 1)
        if verdict is False:
            return _eval(right, env, depth + 1)
        return _eval(left, env, depth + 1) + _eval(right, env, depth + 1)

    m = _CALL.match(src)
    if m is not None and skip_group(src, m.end() - 1) == len(src):
        return [t for arg in _split_top(src[m.end():-1], ",")
                for t in _eval(arg, env, depth + 1)]

    if _IDENT.fullmatch(src):
        return _eval(env[src], env, depth + 1) if src in env else []

    return _harvest(src)


def _dedup(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def class_tokens(raw: str, env: dict[str, str] | None = None) -> list[str]:
    """Every class a class attribute can put on an element.

    ``raw`` is the attribute value exactly as the scanner captured it: a plain
    ``"px-4 py-2"``, a JSX ``{…}`` expression, or a framework directive value
    such as Vue's ``{ active: isOn }`` and ``[base, extra]``.
    """
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("{") or raw.startswith("["):
        return _dedup(_eval(raw, env or {}))
    if raw[:1] == "`" and skip_string(raw, 0) == len(raw):
        return _dedup(_template(raw, env or {}, 0))
    return _tokens(raw)


_RUN = re.compile(r"\S+")


class Rewritable:
    """Where a class attribute may be edited, and what had to be left alone."""

    __slots__ = ("spans", "glued")

    def __init__(self) -> None:
        self.spans: list[tuple[int, int]] = []
        self.glued = 0        # tokens welded to an interpolation, so untouchable


def _chunk_span(src: str, a: int, b: int, at_start: bool, at_end: bool,
                out: Rewritable) -> None:
    """The safely replaceable part of one static chunk of a template literal.

    A token that touches an interpolation is not a class — it is half of one —
    so the chunk is trimmed to the tokens that are whole on both sides. What is
    left is ordinary text in the file and can be swapped for anything; what was
    trimmed is counted, because a transform that silently declines to change
    something reads as a transform that found nothing to change.
    """
    text = src[a:b]
    if "\\" in text or not text.strip():
        return
    runs = [(m.start(), m.end()) for m in _RUN.finditer(text)]
    if not at_start and runs and runs[0][0] == 0:
        runs = runs[1:]
        out.glued += 1
    if not at_end and runs and runs[-1][1] == len(text):
        runs = runs[:-1]
        out.glued += 1
    if runs:
        out.spans.append((a + runs[0][0], a + runs[-1][1]))


def _template_spans(src: str, start: int, end: int, out: Rewritable) -> None:
    body_end = end - 1
    i = last = start + 1
    while i < body_end:
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == "$" and src[i + 1:i + 2] == "{":
            hole = skip_group(src, i + 1)
            _chunk_span(src, last, i, last == start + 1, False, out)
            _scan_rewritable(src, i + 2, hole - 1, out)
            i = last = hole
            continue
        i += 1
    _chunk_span(src, last, body_end, last == start + 1, True, out)


def _scan_rewritable(raw: str, a: int, b: int, out: Rewritable) -> None:
    j = a
    while j < b:
        c = raw[j]
        if c in "\"'":
            end = skip_string(raw, j)
            if end - j >= 2 and "\\" not in raw[j:end]:
                out.spans.append((j + 1, end - 1))
            j = end
            continue
        if c == "`":
            end = skip_string(raw, j)
            _template_spans(raw, j, end, out)
            j = end
            continue
        j += 1


def rewritable(raw: str) -> Rewritable:
    """Where ``raw`` may be edited, plus how many tokens could not be.

    The editable places are the body of a quoted string and the whole tokens of
    a template literal's static text: both are ordinary text in the file, so
    replacing them cannot change what the expression *does*. Escaped strings
    are left out — the offsets of an escape are not the offsets of the text it
    stands for.
    """
    out = Rewritable()
    _scan_rewritable(raw, 0, len(raw), out)
    return out


def rewritable_spans(raw: str) -> list[tuple[int, int]]:
    return rewritable(raw).spans


def _scan_conditional(src: str, a: int, b: int, out: list[tuple[int, int]]) -> None:
    """Record the part of one group's body that only renders conditionally."""
    from_at = -1
    j = a
    while j < b:
        c = src[j]
        if c in "\"'":
            j = skip_string(src, j)
            continue
        if c == "`":
            end = skip_string(src, j)
            i = j + 1
            while i < end - 1:
                if src[i] == "$" and src[i + 1:i + 2] == "{":
                    hole = skip_group(src, i + 1)
                    _scan_conditional(src, i + 2, hole - 1, out)
                    i = hole
                    continue
                i += 1
            j = end
            continue
        if c in "([{":
            end = skip_group(src, j)
            _scan_conditional(src, j + 1, end - 1, out)
            j = end
            continue
        if c == ",":
            # Each argument of a call, and each element of an array, stands on
            # its own: a condition in one does not reach the next.
            if from_at >= 0:
                out.append((from_at, j))
                from_at = -1
            j += 1
            continue
        if from_at < 0 and ((c == "?" and src[j:j + 2] not in ("?.", "??"))
                            or src[j:j + 2] in ("&&", "||", "??")):
            from_at = j
        j += 1
    if from_at >= 0:
        out.append((from_at, b))


def conditional_regions(raw: str) -> list[tuple[int, int]]:
    """Regions of ``raw`` whose classes only apply when a condition holds.

    The transformer needs this to decide where a *new* class may go. Remapping
    an existing class inside a branch is safe — it was already only there under
    that condition — but a class the element gains must land somewhere that
    always renders, or the fix would apply to one state of the UI and not the
    others.
    """
    out: list[tuple[int, int]] = []
    _scan_conditional(raw, 0, len(raw), out)
    return out


def is_conditional(start: int, end: int, regions: list[tuple[int, int]]) -> bool:
    return any(a <= start and end <= b for a, b in regions)
