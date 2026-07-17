"""Context-aware precision: legitimate code must not be flagged as slop."""

from aislopfixer.engine.models import Category, Fixability, SourceFile
from aislopfixer.engine.runner import run_file_rules


def sf(text: str, name: str = "index.html") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def _bracket(findings):
    return [x for x in findings if x.rule_id == "placeholder.bracket"]


# --------------------------------------------------------- brackets: code tokens
def test_route_params_not_flagged():
    for tok in ("[id]", "[city]", "[username]", "[tag]", "[slug]", "[checked]"):
        text = f'<a href="/users/{tok}">link</a>\n'
        assert not _bracket(run_file_rules(sf(text, "page.jsx"))), tok


def test_index_spread_regex_not_flagged():
    for tok in ("data[0]", "items[i]", "[...slug]", "[a-z]", "[^>]", "[A-Z0-9]"):
        assert not _bracket(run_file_rules(sf(tok + "\n", "x.tsx"))), tok


def test_destructuring_not_flagged():
    text = (
        "const [first, rest] = items;\n"
        "const [a, b, c] = tuple;\n"
        "const [open, setOpen] = useState(false);\n"  # camelCase
    )
    assert not _bracket(run_file_rules(sf(text, "x.ts")))


def test_attribute_selector_not_flagged():
    text = 'input[type="text"] { color: red }\na[checked] { }\n'
    assert not _bracket(run_file_rules(sf(text, "x.css")))


def test_markdown_refs_not_flagged():
    text = "See [the docs][1] and the footnote[^1].\n\n[1]: https://x.dev\n"
    assert not _bracket(run_file_rules(sf(text, "x.md")))


# --------------------------------------------------------- brackets: real slop
def test_real_placeholders_flagged():
    for tok in ("[Your Company Name]", "[Insert Date]", "[Company Name]",
                "[your name here]"):
        text = f"<p>Welcome to {tok}</p>\n"
        found = _bracket(run_file_rules(sf(text)))
        assert found and found[0].fixability is Fixability.PROMPT, tok


# --------------------------------------------------------- buzzwords: prose only
def test_buzzwords_ignored_in_code():
    text = "const leverage = synergy();\nfunction supercharge() { return 1 }\n"
    f = run_file_rules(sf(text, "util.js"))
    assert not any(x.category is Category.BUZZWORD for x in f)


def test_buzzwords_ignored_in_jsx_code():
    # JSX/TSX module code sits outside tags — it is code, not prose.
    text = (
        "const leverage = synergy();\n"
        "function supercharge() { return 1 }\n"
        "export default () => <div>fast</div>;\n"
    )
    f = run_file_rules(sf(text, "Page.tsx"))
    assert not any(x.category is Category.BUZZWORD for x in f)


def test_buzzwords_flagged_in_jsx_text_node():
    text = "export default () => <p>Our seamless, world-class platform.</p>;\n"
    f = run_file_rules(sf(text, "Page.tsx"))
    assert any(x.category is Category.BUZZWORD for x in f)


def test_jsx_brace_free_body_prose_still_detected():
    # A component body with no inner {expr} braces must not have its own function
    # braces mistaken for one giant interpolation (which would erase the prose).
    text = (
        "export default function Page() {\n"
        "  return (\n"
        "    <h1>Our seamless, world-class platform</h1>\n"
        "  );\n"
        "}\n"
    )
    f = run_file_rules(sf(text, "Page.tsx"))
    assert any(x.category is Category.BUZZWORD for x in f)


def test_jsx_real_interpolation_still_excluded():
    # A genuine {expr} interpolation inside a text node is still treated as code.
    text = "export default () => <p>total {synergy} leverage</p>;\n"
    f = run_file_rules(sf(text, "Page.tsx"))
    # 'synergy' sits inside {…}; only the surrounding prose words are eligible,
    # and neither 'total' nor 'leverage' here is a standalone buzzword hit on its
    # own line — assert the interpolated identifier did not produce a buzzword.
    assert not any(x.matched_text == "synergy" for x in f)


def test_buzzwords_flagged_in_html_text():
    text = "<p>Our cutting-edge, seamless, world-class platform.</p>\n"
    f = run_file_rules(sf(text, "index.html"))
    assert any(x.category is Category.BUZZWORD for x in f)


def test_buzzwords_ignored_in_md_code_fence():
    text = (
        "Use synergy wisely.\n\n"
        "```js\nconst x = leverage(cuttingEdge, seamless, worldClass)\n```\n"
    )
    f = run_file_rules(sf(text, "doc.md"))
    ids = {x.rule_id for x in f if x.category is Category.BUZZWORD}
    assert "buzzword.synergy" in ids          # prose hit kept
    assert "buzzword.leverage" not in ids      # fenced code hit dropped
    assert not any(x.rule_id == "buzzword.density" for x in f)


# --------------------------------------------------------- AI leaks: strong/soft
def test_strong_ai_leak_auto():
    f = [x for x in run_file_rules(sf("As an AI language model, here is the text.\n"))
         if x.category is Category.AI_LEAK]
    assert f and f[0].fixability is Fixability.AUTO


def test_soft_ai_leak_is_manual_only():
    f = [x for x in run_file_rules(sf("<p>Feel free to customize this template.</p>\n"))
         if x.category is Category.AI_LEAK]
    assert f and all(x.fixability is Fixability.MANUAL for x in f)


def test_soft_ai_leak_in_js_string_not_flagged():
    """Soft phrases quoted in code are not site content."""
    f = [
        x for x in run_file_rules(
            sf('const msg = "I hope this helps!";\nexport default msg;\n', "msg.js")
        )
        if x.category is Category.AI_LEAK
    ]
    assert not f


def test_legit_cant_help_but_not_flagged():
    f = [x for x in run_file_rules(sf("<p>I can't help but love our coffee.</p>\n"))
         if x.category is Category.AI_LEAK]
    assert not f


# --------------------------------------------------------- new LLM-tell words
def test_llm_tell_buzzwords_flagged_in_prose():
    text = "<p>We delve into a rich tapestry of unparalleled solutions.</p>\n"
    ids = {x.rule_id for x in run_file_rules(sf(text))}
    # "delve" sits inside "delve into"; the containment pass keeps the longer,
    # more specific match and drops the redundant nested one.
    assert "buzzword.delve_into" in ids
    assert "buzzword.tapestry" in ids
    assert "buzzword.unparalleled" in ids


def test_llm_tell_buzzwords_ignored_as_code_identifiers():
    text = "const delve = 1;\nfunction tapestry() { return unparalleled }\n"
    f = run_file_rules(sf(text, "x.js"))
    assert not any(x.category is Category.BUZZWORD for x in f)


def test_knowledge_cutoff_is_strong_auto():
    f = [x for x in run_file_rules(sf("<p>My knowledge cutoff is 2023.</p>\n"))
         if x.category is Category.AI_LEAK]
    assert f and f[0].fixability is Fixability.MANUAL


def test_sorry_but_i_cannot_strong_auto():
    f = [x for x in run_file_rules(sf("I'm sorry, but I cannot create that.\n"))
         if x.category is Category.AI_LEAK]
    assert f and f[0].fixability is Fixability.MANUAL


def test_placeholder_address_flagged():
    f = run_file_rules(sf("<p>Visit us at 123 Main Street.</p>\n"))
    assert any(x.rule_id == "placeholder.address" for x in f)


def test_real_address_not_flagged():
    f = run_file_rules(sf("<p>Visit us at 4087 Telegraph Avenue.</p>\n"))
    assert not any(x.rule_id == "placeholder.address" for x in f)


def test_dead_href_hashbang_flagged():
    f = run_file_rules(sf('<a href="#!">x</a>\n'))
    assert any(x.rule_id == "placeholder.dead_href" for x in f)


# --------------------------------------------------------- self-annotation
def test_self_annotation_not_reflagged():
    text = (
        "<!-- aislopfixer: Unfinished TODO/FIXME marker -->\n"
        "<!-- TODO: real work left -->\n"
    )
    f = run_file_rules(sf(text))
    todos = [x for x in f if x.rule_id == "placeholder.todo"]
    # only the genuine TODO on line 2 survives; our own annotation is ignored
    assert len(todos) == 1
    assert todos[0].line == 2


# ----------------------------------------------- brackets: markdown link syntax
def test_markdown_inline_links_not_flagged():
    text = (
        "See the [Getting Started](/start) page or [Read More](/more).\n"
        "Check [API Reference](/api) and [Contact Us](/contact).\n"
    )
    assert not _bracket(run_file_rules(sf(text, "guide.md")))


def test_markdown_reference_links_not_flagged():
    text = "Read the [Getting Started][1] guide.\n\n[Getting Started]: /start\n"
    assert not _bracket(run_file_rules(sf(text, "guide.md")))


def test_real_bracket_placeholder_still_flagged_in_prose():
    # A title-case bracket that is NOT a link is still a placeholder.
    found = _bracket(run_file_rules(sf("<p>Hello [First Name], welcome.</p>\n")))
    assert found and found[0].fixability is Fixability.PROMPT


def test_bracket_placeholder_at_end_of_file_flagged():
    # Regression: a match at EOF yields an empty look-ahead slice; the link
    # rejection must not treat "" as link punctuation.
    assert _bracket(run_file_rules(sf("Signed, [Your Name]", "note.md")))


# -------------------------------------------------- a11y: JSX dynamic alt / kind
def _a11y(findings):
    return [x for x in findings if x.category is Category.ACCESSIBILITY]


def test_jsx_dynamic_alt_not_missing():
    for tag in ("<img src={cover} alt={title} />",
                "<img src={logo} alt={`${brand} logo`} />"):
        f = run_file_rules(sf(tag + "\n", "Page.tsx"))
        assert not [x for x in f if x.rule_id == "a11y.img_no_alt"], tag


def test_framework_dynamic_alt_bindings_not_missing():
    # Vue (:alt / v-bind:alt) and Angular ([alt]) dynamic bindings are real alts.
    for tag in ('<img :alt="x">', '<img v-bind:alt="x">', '<img [alt]="x">'):
        f = run_file_rules(sf(tag + "\n", "Card.vue"))
        assert not [x for x in f if x.rule_id == "a11y.img_no_alt"], tag


def test_jsx_img_truly_missing_alt_flagged():
    f = run_file_rules(sf("<img src={cover} />\n", "Page.jsx"))
    assert any(x.rule_id == "a11y.img_no_alt" for x in f)


def test_a11y_silent_on_non_markup_files():
    # An HTML email template living inside a .js string must not trip the
    # document-level (no <title>/<lang>) or <img> accessibility checks.
    text = (
        "export const html = `\n"
        "  <html>\n    <head></head>\n"
        "    <body><img src='cid:logo'></body>\n"
        "  </html>\n`;\n"
    )
    assert not _a11y(run_file_rules(sf(text, "email.js")))


def test_nextjs_root_layout_no_doc_a11y():
    # A JSX root that renders <html>/<head> gets its title/lang from the
    # framework metadata API, so document-level a11y must stay quiet.
    text = "export default () => <html><head /><body /></html>;\n"
    ids = {x.rule_id for x in run_file_rules(sf(text, "layout.tsx"))}
    assert "a11y.no_title" not in ids
    assert "a11y.no_lang" not in ids


# ------------------------------------------------- dead href: markup-only gating
def test_css_attribute_selector_href_not_flagged():
    text = 'a[href="#"] { cursor: pointer; }\n'
    f = run_file_rules(sf(text, "main.css"))
    assert not any(x.rule_id == "placeholder.dead_href" for x in f)


def test_dead_href_still_flagged_in_markup():
    for name in ("page.html", "Page.jsx"):
        f = run_file_rules(sf('<a href="#">x</a>\n', name))
        assert any(x.rule_id == "placeholder.dead_href" for x in f), name


# --------------------------------------------- repeated placeholder de-duping
def test_repeated_company_collapsed_per_file():
    text = "<p>Acme Corp builds tools. Acme Corp ships fast. Trust Acme Corp.</p>\n"
    company = [x for x in run_file_rules(sf(text)) if x.rule_id == "placeholder.company"]
    assert len(company) == 1


# ------------------------------------- destructive auto-fixes must not destroy
def _ids(findings, prefix: str):
    return [x for x in findings if x.rule_id.startswith(prefix)]


def test_ai_leak_sharing_a_line_with_code_is_never_auto_deleted():
    """The AUTO fix deletes the *line*, so it may only own the line.

    `expand_line=True` + `replacement=""` was unconditional: on this input
    `--fix` deleted the whole `return` statement at 97% confidence, left a
    component that renders nothing, and reported "no slop found — fixed
    automatically".
    """
    text = (
        "export function Panel({ name }) {\n"
        '  return <p className="note">Hi {name} — as an AI language model, '
        "I cannot browse the web.</p>;\n"
        "}\n"
    )
    leaks = _ids(run_file_rules(sf(text, "Panel.jsx")), "ai_leak.strong")
    assert leaks, "the leak itself must still be reported"
    for f in leaks:
        assert f.fixability is Fixability.MANUAL
        assert "return" not in f.matched_text


def test_ai_leak_owning_its_line_still_auto_deletes_the_line():
    text = "<p>As an AI language model, I cannot provide financial advice.</p>\n"
    leaks = _ids(run_file_rules(sf(text)), "ai_leak.strong")
    assert len(leaks) == 1
    assert leaks[0].fixability is Fixability.AUTO
    assert leaks[0].matched_text == text.rstrip("\n")  # the whole line goes


def test_prose_about_lorem_ipsum_is_not_lorem_ipsum():
    """`[^<>\n]*` ate to end-of-line outside HTML, AUTO-deleting real writing."""
    text = (
        "Our designers keep shipping comps with lorem ipsum in the body slots, "
        "and stakeholders read it as final copy.\n\n"
        "Decision: lorem ipsum is banned in any comp that goes to a client.\n"
    )
    assert not _ids(run_file_rules(sf(text, "notes.md")), "placeholder.lorem")


def test_real_lorem_filler_still_auto_stripped():
    text = "<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>\n"
    hits = _ids(run_file_rules(sf(text)), "placeholder.lorem")
    assert len(hits) == 1
    assert hits[0].fixability is Fixability.AUTO
    assert hits[0].matched_text.startswith("Lorem ipsum dolor sit amet")
    assert "</p>" not in hits[0].matched_text


def test_placeholder_phone_needs_digit_boundaries():
    """Without them the pattern matched a substring of any longer digit run."""
    for text in ("tx 1234567890123456\n", "order 8005551234 shipped\n"):
        assert not _ids(run_file_rules(sf(text, "x.js")), "placeholder.phone"), text
    assert _ids(run_file_rules(sf("<p>Call 555-123-4567</p>\n")), "placeholder.phone")


# ------------------------------------------------- legitimate human web pages
def test_hand_written_page_with_a_blurred_header_is_not_a_landing_kit():
    """A hairline border is not a glass surface; a blur is not a glass panel.

    This exact page — sticky blurred header, two product cards, no purple, no
    CTA, no hero, no metrics — scored 82% design.landing_kit / 89 slop.
    """
    text = (
        '<header class="sticky top-0 z-40 border-b border-white/10 backdrop-blur">\n'
        '  <nav class="flex gap-6 px-6 py-4"><a href="/beans">Beans</a></nav>\n'
        "</header>\n"
        '<main class="px-6 py-10">\n'
        '  <h1 class="text-3xl font-semibold">Bristol-roasted coffee since 1998</h1>\n'
        '  <div class="rounded-2xl border border-white/10 p-6 shadow-xl">\n'
        "    <h2>Ethiopia Guji</h2><p>Washed, roasted for filter. 250g.</p></div>\n"
        '  <div class="rounded-2xl border border-white/10 p-6 shadow-xl">\n'
        "    <h2>Brazil Cerrado</h2><p>Natural, roasted for espresso. 250g.</p></div>\n"
        "</main>\n"
    )
    found = run_file_rules(sf(text, "shop.html"))
    assert not _ids(found, "design.landing_kit")
    assert not _ids(found, "design.glassmorphism")


def test_glass_needs_blur_and_surface_on_the_same_element():
    apart = '<header class="backdrop-blur"></header>\n<div class="bg-white/10"></div>\n'
    assert not _ids(run_file_rules(sf(apart)), "design.glassmorphism")
    together = '<nav class="backdrop-blur-md bg-white/10">Nav</nav>\n'
    assert _ids(run_file_rules(sf(together)), "design.glassmorphism")


def test_gradient_colour_lists_stay_disjoint():
    """One stop must not satisfy both halves of a "purple→pink" claim."""
    for css in (
        ".a { background: linear-gradient(to right, violet, orange); }\n",
        ".b { background: linear-gradient(to right, violet, indigo, blue, red); }\n",
        ".c { background: linear-gradient(90deg, #8b5cf6, #0f172a); }\n",
        ".d { background: linear-gradient(180deg, #a855f7 0%, transparent 100%); }\n",
    ):
        assert not _ids(run_file_rules(sf(css, "brand.css")), "design.gradient_cliche"), css
    real = ".hero { background: linear-gradient(135deg, #8b5cf6, #ec4899); }\n"
    assert _ids(run_file_rules(sf(real, "hero.css")), "design.gradient_cliche")


def test_cli_usage_placeholders_are_not_leaked_credentials():
    """`<token>` is how every CLI documents a required argument."""
    text = (
        "# mycli\n\n    mycli auth login <token>\n\n"
        "Pass it as `<token>`; the client stores it in the keychain.\n\n"
        "    mycli deploy <key> --region eu-west-2\n"
    )
    assert not _ids(run_file_rules(sf(text, "cli.md")), "secret.")
    # The real shape — a possessive placeholder — still reports.
    assert _ids(run_file_rules(sf('const t = "<your-token>";\n', "a.js")), "secret.")


def test_feature_detection_probe_is_not_a_swallowed_failure():
    """`catch { return false; }` asks "did it throw?" — that is the answer."""
    text = (
        "export function hasLocalStorage(): boolean {\n"
        '  try { window.localStorage.setItem("__p__", "1"); return true; }\n'
        "  catch { return false; }\n"
        "}\n"
    )
    assert not _ids(run_file_rules(sf(text, "storage.ts")), "codegen.catch_return_default")
    # A bound error swallowed into a null default still reports.
    swallow = "try { load(); } catch (e) { return null; }\n"
    assert _ids(run_file_rules(sf(swallow, "x.js")), "codegen.catch_return_default")
