"""The parse layer: markup scanning, class decoding, CSS, component resolution."""

from __future__ import annotations

from aislopfixer.design.models import Axis, Origin
from aislopfixer.design.parse import parse_document, resolve_components
from aislopfixer.design.parse.classes import decode_class, split_variants
from aislopfixer.design.parse.css import class_index, decl_from_css, parse_css
from aislopfixer.design.parse.expr import class_tokens
from aislopfixer.design.parse.theme import ThemeIndex, load_theme, parse_theme
from aislopfixer.design.parse.markup import extract_classes, extract_inline_style, parse_markup
from aislopfixer.design.render import render_documents


def doc(name: str, text: str):
    return parse_document(name, f"/abs/{name}", text)


# ------------------------------------------------------------------- markup
def test_html_tree_has_parents_and_text():
    d = doc("a.html", "<section class='x'><h2>Hello</h2><p>World</p></section>")
    tags = [el.tag for el in d.elements]
    assert tags == ["section", "h2", "p"]
    assert d.elements[1].parent == 0
    assert d.elements[1].own_text == "Hello"
    assert d.elements[0].own_text == "Hello World"


def test_closing_tags_pop_the_stack_in_jsx():
    """Regression: guarding `</` as an operator nested a whole page in one node."""
    d = doc("a.jsx", "export const A = () => (\n  <div>\n    <h1>Hi</h1>\n    <p>There</p>\n  </div>\n)")
    depths = {el.tag: el.depth for el in d.elements}
    assert depths == {"div": 0, "h1": 1, "p": 1}


def test_type_arguments_are_not_elements():
    text = (
        "const [a, setA] = useState<Foo>(null);\n"
        "let m: Record<string, number> = {};\n"
        "const list: Array<string[]> = [];\n"
        "export const V = () => <span>ok</span>;\n"
    )
    d = doc("a.tsx", text)
    assert [el.tag for el in d.elements] == ["span"]


def test_jsx_text_after_a_word_still_parses_as_a_tag():
    d = doc("a.jsx", "const V = () => <p>hello<br/>world</p>;")
    assert [el.tag for el in d.elements] == ["p", "br"]


def test_tags_inside_string_literals_are_skipped():
    d = doc("a.js", 'const s = "<div class=\'x\'>not markup</div>";')
    assert d.elements == []


def test_class_expression_yields_every_literal():
    assert extract_classes('{cn("px-4 py-2", open && "bg-red-500")}') == [
        "px-4", "py-2", "bg-red-500",
    ]


def test_inline_style_both_dialects():
    assert extract_inline_style("color: red; margin-top: 4px") == {
        "color": "red", "margin-top": "4px",
    }
    assert extract_inline_style("{{ marginTop: 8, color: 'red' }}") == {
        "margin-top": "8", "color": "red",
    }


def test_void_and_self_closing_do_not_nest():
    d = doc("a.html", "<div><img src='x'><br><span>y</span></div>")
    assert [el.depth for el in d.elements] == [0, 1, 1, 1]


def test_unclosed_tag_does_not_raise():
    els = parse_markup("<section><div>", ".html")
    assert [el.tag for el in els] == ["section", "div"]


# ------------------------------------------------------------------ classes
def test_split_variants_respects_brackets():
    assert split_variants("md:hover:px-4") == (["md", "hover"], "px-4")
    assert split_variants("bg-[url(a:b)]") == ([], "bg-[url(a:b)]")


def test_default_values_are_not_decisions():
    d = decode_class("py-20")
    assert (d.axis, d.prop, d.value, d.origin) == (
        Axis.SPACE, "padding-y", "20", Origin.DEFAULT)


def test_arbitrary_value_is_a_decision():
    assert decode_class("text-[2.75rem]").origin is Origin.ARBITRARY
    assert decode_class("tracking-[-0.02em]").origin is Origin.ARBITRARY


def test_theme_token_is_the_strongest_signal():
    d = decode_class("bg-surface")
    assert (d.axis, d.prop, d.origin) == (Axis.COLOR, "background", Origin.TOKEN)
    assert Origin.TOKEN.decision_weight > Origin.DEFAULT.decision_weight


def test_side_border_is_a_name_not_a_value():
    """Regression: `border-b` decoded as width "b", i.e. a fake project token."""
    d = decode_class("border-b")
    assert (d.axis, d.prop, d.origin) == (Axis.SHAPE, "border-b", Origin.DEFAULT)
    assert decode_class("border-t-2").prop == "border-top"
    assert decode_class("border-t-2").origin is Origin.DEFAULT
    assert decode_class("rounded-t-lg").prop == "radius-t"
    assert decode_class("rounded-t-lg").origin is Origin.DEFAULT


def test_colour_and_size_share_the_text_prefix():
    assert decode_class("text-4xl").axis is Axis.TYPE
    assert decode_class("text-gray-900").axis is Axis.COLOR
    assert decode_class("text-center").prop == "text-align"


def test_longest_prefix_wins_over_colour():
    assert decode_class("bg-gradient-to-r").axis is Axis.MATERIAL
    assert decode_class("bg-white/10").axis is Axis.COLOR
    assert decode_class("shadow-lg").axis is Axis.MATERIAL
    assert decode_class("shadow-blue-500/50").axis is Axis.COLOR


def test_variant_is_kept_separately():
    d = decode_class("md:grid-cols-3")
    assert d.variant == "md" and d.value == "3"


def test_unknown_utility_is_dropped_not_guessed():
    assert decode_class("prose") is None
    assert decode_class("") is None


# ---------------------------------------------------------------------- css
def test_css_rules_and_custom_properties():
    rules, custom = parse_css(":root { --color-ink: #111; }\n.card { padding: 2rem; }")
    assert custom["--color-ink"] == "#111"
    assert any(r.selector == ".card" for r in rules)


def test_css_declarations_normalise_onto_the_same_axes_as_utilities():
    decls = decl_from_css("padding-block", "5rem")
    assert decls[0].axis is Axis.SPACE and decls[0].prop == "padding-y"
    # 5rem *is* `py-20`. Same decision, same absence of one, same origin —
    # otherwise a project scores higher for spelling its defaults in CSS.
    assert decls[0].value == "20" and decls[0].origin is Origin.DEFAULT
    authored = decl_from_css("padding-block", "4.5rem")
    assert authored[0].value == "4.5rem"
    assert authored[0].origin is Origin.LITERAL


def test_a_css_shorthand_lands_on_the_axis_a_utility_would():
    got = {(d.prop, d.value) for d in decl_from_css("padding", "5rem 0")}
    assert got == {("padding-y", "20"), ("padding-x", "0")}
    assert {(d.prop, d.value) for d in decl_from_css("margin", "0 auto")} == \
        {("margin-y", "0"), ("margin-x", "auto")}


def test_a_shipped_value_in_css_is_a_default_and_an_authored_one_is_not():
    def one(prop, value):
        return decl_from_css(prop, value)[0]

    assert (one("font-size", "36px").value, one("font-size", "36px").origin) == \
        ("4xl", Origin.DEFAULT)
    assert one("font-size", "2.75rem").origin is Origin.LITERAL
    assert one("border-radius", "16px").value == "2xl"
    assert one("max-width", "1200px").origin is Origin.LITERAL   # not 80rem
    assert one("text-align", "center").value == "text-center"
    assert one("grid-template-columns", "repeat(3, 1fr)").value == "3"
    assert one("grid-template-columns", "2fr 1fr").origin is Origin.LITERAL


def test_var_reference_counts_as_a_token():
    assert decl_from_css("color", "var(--ink)")[0].origin is Origin.TOKEN


def test_border_shorthand_fans_out_to_shape_and_colour():
    axes = {d.axis for d in decl_from_css("border", "1px solid #e5e7eb")}
    assert axes == {Axis.SHAPE, Axis.COLOR}


def test_at_rule_nesting_is_flattened():
    rules, _ = parse_css("@media (min-width:768px) { .a { gap: 1rem; } }")
    assert rules and rules[0].selector == ".a" and rules[0].at.startswith("@media")


def test_class_index_only_takes_single_class_selectors():
    rules, _ = parse_css(".a { color: red } .a .b { color: blue }")
    assert set(class_index(rules)) == {"a"}


# ------------------------------------------------------------- theme config
def test_theme_reads_both_dialects():
    v4, _ = parse_theme("app.css",
                        "@theme {\n  --color-ink: #111;\n  --text-lg: 1.1rem;\n}")
    assert ("color", "ink") in v4 and ("font-size", "lg") in v4
    v3, _ = parse_theme(
        "tailwind.config.js",
        "module.exports = { theme: { extend: { fontSize: { lg: '1.1rem' },"
        " colors: { paper: '#f7f5f2' } } } }",
    )
    assert ("font-size", "lg") in v3 and ("color", "paper") in v3


def test_theme_ignores_scales_no_utility_expresses():
    """`screens` is a real Tailwind scale with no Decl prop — crediting it
    would invent a decision the class decoder can never point at."""
    pairs, tuned = parse_theme(
        "tailwind.config.js",
        "export default { theme: { extend: { screens: { tablet: '820px' } } } }",
    )
    assert not pairs and not tuned


def test_theme_records_which_sizes_carry_their_own_leading():
    """A ramp that states its leading is tuned, and the display tell must not
    accuse it. A ramp of bare values is not, and the tell still applies."""
    _, tuned = parse_theme(
        "tailwind.config.js",
        "module.exports = { theme: { fontSize: {"
        " display: ['4rem', { lineHeight: '0.95', letterSpacing: '-0.03em' }],"
        " plain: '2rem' } } }",
    )
    assert tuned == {"display"}
    _, v4_tuned = parse_theme(
        "app.css",
        "@theme {\n  --text-4xl: 2.25rem;\n  --text-4xl--line-height: 1.1;\n"
        "  --text-5xl: 3rem;\n}",
    )
    assert v4_tuned == {"4xl"}


def test_theme_only_the_redefined_key_becomes_a_decision():
    theme = ThemeIndex(pairs=frozenset({("font-size", "lg")}))
    assert decode_class("text-lg", theme).origin is Origin.TOKEN
    assert decode_class("text-4xl", theme).origin is Origin.DEFAULT
    # And with no config at all nothing moves.
    assert decode_class("text-lg").origin is Origin.DEFAULT


def test_theme_spacing_key_covers_every_spacing_utility():
    theme = ThemeIndex(pairs=frozenset({("spacing", "band")}))
    assert decode_class("py-band", theme).origin is Origin.TOKEN
    assert decode_class("gap-band", theme).origin is Origin.TOKEN
    assert decode_class("py-20", theme).origin is Origin.DEFAULT


def test_theme_colour_family_covers_its_shades():
    theme = ThemeIndex(pairs=frozenset({("color", "brand")}))
    assert decode_class("bg-brand-500", theme).origin is Origin.TOKEN
    assert decode_class("bg-gray-100", theme).origin is Origin.DEFAULT


def test_theme_cache_is_keyed_on_the_project():
    """Regression: a project-blind cache handed one project's decisions to the
    next one scanned in the same process."""
    a = ThemeIndex(pairs=frozenset({("font-size", "sm")}))
    assert decode_class("text-sm", a).origin is Origin.TOKEN
    assert decode_class("text-sm", ThemeIndex()).origin is Origin.DEFAULT


def test_load_theme_reads_a_whole_project():
    class Src:
        def __init__(self, rel_path, text):
            self.rel_path, self.text = rel_path, text

    theme = load_theme([
        Src("tailwind.config.js", "module.exports={theme:{extend:{spacing:{band:'7rem'}}}}"),
        Src("src/app.css", "@theme { --color-paper: #f7f5f2; }"),
        Src("src/page.html", "<div class='p-4'></div>"),
    ])
    assert ("spacing", "band") in theme.pairs
    assert ("color", "paper") in theme.pairs
    assert theme.sources == ("src/app.css", "tailwind.config.js")


def test_style_block_inside_html_is_parsed():
    d = doc("a.html", "<style>.card { border-radius: 12px }</style><div class='card'>x</div>")
    assert d.css_rules
    div = next(el for el in d.elements if el.tag == "div")
    assert any(dd.prop == "radius" for dd in div.decls)


# ------------------------------------------------- CSS Modules / CSS-in-JS
def _resolved(*files):
    from aislopfixer.design.parse.styles import resolve_styles
    docs = [doc(name, text) for name, text in files]
    resolve_styles(docs)
    return docs


def test_a_css_module_class_reaches_the_element_that_imports_it():
    page, _sheet = _resolved(
        ("app/page.jsx",
         "import s from './page.module.css'\n"
         "export default () => <div className={s.card}>hi</div>"),
        ("app/page.module.css", ".card { border-radius: 14px; padding: 2.25rem }"),
    )
    card = page.elements[0]
    assert {d.prop for d in card.decls} >= {"radius", "padding"}
    assert card.module_classes == ["card"]


def test_an_unresolvable_module_import_is_counted_not_swallowed():
    page, = _resolved(
        ("app/page.jsx",
         "import s from '@/styles/Card.module.css'\n"
         "export default () => <div className={s.card} />"),
    )
    assert page.unresolved_modules == 1


def test_a_styled_component_is_a_definition_with_a_tag_and_declarations():
    from aislopfixer.design.parse.styles import scan_styled

    defs = scan_styled(
        "const Band = styled.section`\n  padding: 5rem 0;\n"
        "  &:hover { color: #111827; }\n`\n"
    )
    assert len(defs) == 1
    assert defs[0].name == "Band" and defs[0].tag == "section"
    # The nested block's declaration counts; its selector does not.
    assert {(d.prop, d.value) for d in defs[0].decls} >= {
        ("padding-y", "20"), ("color", "gray-900")}


def test_an_interpolated_css_in_js_value_is_counted_not_guessed():
    from aislopfixer.design.parse.styles import scan_styled

    defs = scan_styled("const B = styled.a`color: ${p => p.theme.accent}; padding: 1rem;`")
    assert defs[0].unreadable == 1
    assert all(d.prop != "color" for d in defs[0].decls)


def test_a_styled_usage_renders_the_tag_it_was_built_from():
    docs = _resolved(
        ("src/App.jsx",
         "import styled from 'styled-components'\n"
         "const Title = styled.h2`font-size: 36px;`\n"
         "export default () => <div><Title>Features</Title></div>"),
    )
    resolve_components(docs)
    usage = next(el for el in docs[0].elements if el.tag == "Title")
    assert usage.renders_tag == "h2"
    out = render_documents(docs)[0]
    assert any(el.tag == "h2" for el in out.elements)


# --------------------------------------------------------------- components
def test_component_usage_inherits_what_it_renders():
    from aislopfixer.design.parse import resolve_components

    page = doc("page.jsx", (
        "function Section({children}) {\n"
        "  return <section className='py-20'><div className='max-w-7xl'>{children}</div></section>;\n"
        "}\n"
        "export default function Page() {\n"
        "  return <main><Section>a</Section><Section>b</Section></main>;\n"
        "}\n"
    ))
    resolve_components([page])
    usages = [el for el in page.elements if el.tag == "Section" and el.inherited]
    assert len(usages) == 2
    assert any(d.prop == "padding-y" and d.value == "20"
               for d in usages[0].rendered)
    assert page.sections, "a component rendering <section> counts as a band"


# -------------------------------------------------------- class expressions
def test_template_literal_keeps_its_static_classes():
    """Regression: an interpolation used to swallow the band padding with it."""
    assert class_tokens('{`py-20 ${tone === "muted" ? "bg-gray-50" : "bg-white"}`}') == [
        "py-20", "bg-gray-50", "bg-white",
    ]


def test_a_token_glued_to_an_interpolation_is_not_a_class():
    assert class_tokens("{`py-${n} gap-8`}") == ["gap-8"]


def test_a_bound_prop_picks_one_branch():
    raw = '{`py-20 ${tone === "muted" ? "bg-gray-50" : "bg-white"}`}'
    assert class_tokens(raw, {"tone": '"muted"'}) == ["py-20", "bg-gray-50"]
    assert class_tokens(raw, {"tone": "undefined"}) == ["py-20", "bg-white"]


def test_a_condition_operand_is_not_a_class():
    assert class_tokens('{tone === "muted" ? "a" : "b"}') == ["a", "b"]


def test_object_syntax_yields_its_keys():
    assert class_tokens('{{ "is-open": open, active: true, off: false }}') == [
        "is-open", "active",
    ]


def test_unreadable_expressions_still_fall_back_to_the_literals():
    assert class_tokens('{lookup[kind].className + " px-4"}') == ["px-4"]


# ------------------------------------------------------------- render tree
def render(*files):
    docs = [doc(name, text) for name, text in files]
    resolve_components(docs)
    return render_documents(docs)


def test_a_page_without_components_is_returned_untouched():
    d = doc("a.html", "<section class='py-20'><h2>Hi</h2></section>")
    assert render_documents([d])[0] is d


def test_component_usages_become_what_they_render():
    page = doc("page.jsx", (
        "function Section({tone, children}) {\n"
        "  return <section className={`py-20 ${tone === 'muted' ? 'bg-gray-50' : 'bg-white'}`}>"
        "<div className='mx-auto text-center'>{children}</div></section>;\n"
        "}\n"
        "export default function Page() {\n"
        "  return <main><Section><h1>One</h1></Section>"
        "<Section tone='muted'><h2>Two</h2></Section></main>;\n"
        "}\n"
    ))
    resolve_components([page])
    out = render_documents([page])[0]
    tags = [el.tag for el in out.elements]
    assert tags == ["main", "section", "div", "h1", "section", "div", "h2"]
    assert "bg-white" in out.elements[1].classes
    assert "bg-gray-50" in out.elements[4].classes, "the passed prop picks the branch"
    assert out.elements[1].own_text == "One", "text rolls back up the virtual tree"


def test_a_map_over_a_readable_array_repeats_its_child():
    page = doc("page.jsx", (
        "const ITEMS = [{t: 'a'}, {t: 'b'}, {t: 'c'}];\n"
        "function Card() { return <article className='p-6'><span/></article>; }\n"
        "export default function Page() {\n"
        "  return <div className='grid'>{ITEMS.map((i) => <Card key={i.t} />)}</div>;\n"
        "}\n"
    ))
    resolve_components([page])
    out = render_documents([page])[0]
    assert [el.tag for el in out.elements].count("article") == 3


def test_a_map_over_an_unreadable_array_repeats_once():
    """No guessing: an array the source cannot show us renders one child."""
    page = doc("page.jsx", (
        "function Card() { return <article className='p-6'/>; }\n"
        "export default function Page({rows}) {\n"
        "  return <div className='grid'>{rows.map((i) => <Card key={i} />)}</div>;\n"
        "}\n"
    ))
    resolve_components([page])
    out = render_documents([page])[0]
    assert [el.tag for el in out.elements].count("article") == 1


def test_a_component_that_uses_itself_does_not_recurse_forever():
    page = doc("page.jsx", (
        "function Node() { return <li><Node /></li>; }\n"
        "export default function Page() { return <ul><Node /></ul>; }\n"
    ))
    resolve_components([page])
    out = render_documents([page])[0]
    # The second turn is left as the usage itself rather than expanded again:
    # stopping short under-reports the page, inventing a level corrupts it.
    assert [el.tag for el in out.elements] == ["ul", "li", "Node"]


def test_the_authored_tree_is_never_mutated():
    page = doc("page.jsx", (
        "function Card() { return <article className='p-6'/>; }\n"
        "export default function Page() { return <div><Card /><Card /></div>; }\n"
    ))
    resolve_components([page])
    before = [el.tag for el in page.elements]
    render_documents([page])
    assert [el.tag for el in page.elements] == before


# ------------------------------------------------------ single-file components
def test_a_vue_template_is_markup_not_raw_text():
    """Regression: `<template>` as a raw tag made every .vue file measure empty."""
    d = doc("a.vue", (
        "<template>\n"
        "  <section class='py-20' :class=\"{ 'bg-gray-50': muted }\">\n"
        "    <h2 class='text-4xl'>Features</h2>\n"
        "  </section>\n"
        "</template>\n"
        "<script setup>const a = 1 < 2</script>\n"
        "<style scoped>.card { border-radius: 14px }</style>\n"
    ))
    tags = [el.tag for el in d.elements]
    assert "section" in tags and "h2" in tags
    section = next(el for el in d.elements if el.tag == "section")
    assert section.classes == ["py-20", "bg-gray-50"], "both class attributes count"
    assert d.css_rules, "<style scoped> still reaches the CSS parser"


def test_an_html_template_stays_inert():
    d = doc("a.html", "<template><div class='x'>y</div></template><p class='z'>q</p>")
    assert [el.tag for el in d.elements] == ["template", "p"]


def test_svelte_class_directives_are_classes():
    d = doc("a.svelte", "<div class='wrap' class:active={on} class:big={n > 2}>x</div>")
    assert d.elements[0].classes == ["wrap", "active", "big"]


def test_astro_frontmatter_is_not_markup():
    d = doc("a.astro", "---\nconst x = a <b && c> d;\n---\n<section class='py-24'>hi</section>\n")
    assert [el.tag for el in d.elements] == ["section"]
    assert d.elements[0].line == 4


def test_astro_class_list_takes_an_array():
    d = doc("a.astro", "---\n---\n<div class:list={['py-8', on && 'bg-white']}>x</div>\n")
    assert d.elements[0].classes == ["py-8", "bg-white"]


def test_a_single_file_component_is_named_after_its_file():
    page = doc("Page.svelte", "<div class='wrap'><Card /><Card /></div>")
    card = doc("Card.svelte", "<article class='p-6'><span/><em/></article>")
    out = {d.rel_path: r for d, r in
           zip([page, card], render_documents([page, card]))}
    assert [el.tag for el in out["Page.svelte"].elements].count("article") == 2
    assert out["Card.svelte"].elements == [], "a used component is not also a page"


def test_a_vue_slot_takes_the_usage_children():
    section = doc("Band.vue", (
        "<template><section :class=\"['py-20', muted ? 'bg-gray-50' : 'bg-white']\">"
        "<div class='mx-auto'><slot /></div></section></template>\n"
        "<script setup>defineProps({ muted: Boolean });</script>\n"
    ))
    page = doc("App.vue", (
        "<template><main><Band><h1 class='text-5xl'>A</h1></Band>"
        "<Band muted><h2 class='text-4xl'>B</h2></Band></main></template>\n"
    ))
    out = render_documents([section, page])[1]
    tags = [el.tag for el in out.elements]
    assert tags == ["main", "section", "div", "h1", "section", "div", "h2"]
    assert "bg-white" in out.elements[1].classes
    assert "bg-gray-50" in out.elements[4].classes, "a bare prop is a true boolean"


def test_a_v_for_over_a_readable_array_repeats():
    grid = doc("Grid.vue", (
        "<template><div class='grid'>"
        "<Cell v-for=\"item in items\" :key=\"item.id\" /></div></template>\n"
        "<script setup>defineProps({ items: Array });</script>\n"
    ))
    cell = doc("Cell.vue", "<template><article class='p-6'><b/><i/></article></template>")
    page = doc("App.vue", (
        "<template><main><Grid :items=\"ROWS\" /></main></template>\n"
        "<script setup>const ROWS = [{id:1},{id:2},{id:3}];</script>\n"
    ))
    out = render_documents([grid, cell, page])[2]
    assert [el.tag for el in out.elements].count("article") == 3


# --------------------------------------------------------------------- mdx
def test_mdx_frontmatter_and_code_fences_are_not_markup():
    """An MDX page is JSX with markdown around it — and the markdown lies.

    A fenced block documents an API; the JSX in it never renders. An autolink
    (`<https://…>`) is not a tag either. Both were read as elements, which gave
    a docs page a vocabulary drawn from its own code samples.
    """
    page = doc("page.mdx", (
        "---\ntitle: Docs\nlayout: <Weird />\n---\n\n"
        "# Heading\n\nSee <https://example.com> for more.\n\n"
        "```tsx\n<div className=\"px-4 py-20 bg-indigo-600\">sample</div>\n```\n\n"
        "<Callout class=\"p-6 rounded-xl\">Real markup</Callout>\n"
    ))
    tags = [el.tag for el in page.elements]
    assert tags == ["Callout"], tags
    assert "px-4" not in {c for el in page.elements for c in el.classes}


def test_mdx_offsets_still_point_at_the_original_source():
    """Masking is length-preserving: the transformer writes into `doc.text`."""
    text = ("`code`\n\n<div class=\"px-4\">x</div>\n")
    page = doc("a.mdx", text)
    el = page.elements[0]
    start, end = el.class_span
    assert text[start:end] == "px-4"


# ------------------------------------------------- one design, two dialects
def test_an_arbitrary_value_on_a_shipped_step_is_not_a_decision():
    """`py-[2.5rem]` is `py-10`, and `padding: 2.5rem` always decoded as one.

    The utility spelling never went through the same table, so the same value
    was a decision in a class list and a default in a stylesheet — eight points
    of difference between the two halves of one design.
    """
    shipped = decode_class("py-[2.5rem]")
    assert shipped.value == "10" and shipped.origin is Origin.DEFAULT
    # What the escape hatch is actually for still survives it.
    authored = decode_class("text-[2.75rem]")
    assert authored.origin is Origin.ARBITRARY


def test_a_symmetric_longhand_pair_is_one_decision():
    """`padding-top: 2.5rem; padding-bottom: 2.5rem` is `py-10`, once."""
    from aislopfixer.design.parse.css import rule_decls

    folded = rule_decls({"padding-top": "2.5rem", "padding-bottom": "2.5rem"})
    assert [(d.prop, d.value) for d in folded] == [("padding-y", "10")]
    # Different values are two decisions in either dialect.
    apart = rule_decls({"padding-top": "7.5rem", "padding-bottom": "3.25rem"})
    assert {d.prop for d in apart} == {"padding-top", "padding-bottom"}


def test_an_external_stylesheet_reaches_the_elements_it_styles():
    """A rule in `site.css` styled nothing at all until this.

    Only same-file `<style>` blocks were indexed, so a plain HTML page with a
    stylesheet measured as a page with no declarations — no rhythm, no grids,
    no container. Every structural metric was reading an unstyled document.
    """
    from aislopfixer.design.parse import resolve_stylesheets

    page = doc("index.html", "<section class='band'><div class='shell'>x</div></section>")
    sheet = doc("site.css", ".band { padding: 5rem 0 } .shell { max-width: 68rem }")
    assert not page.elements[0].decls
    resolve_stylesheets([page, sheet])
    assert ("padding-y", "20") in {(d.prop, d.value) for d in page.elements[0].decls}
    assert ("max-width", "68rem") in {(d.prop, d.value) for d in page.elements[1].decls}
