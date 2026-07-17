"""Tests for the AI-slop visual-design rules (engine/rules/design_slop.py)."""

from aislopfixer.engine.models import SourceFile
from aislopfixer.engine.runner import run_file_rules


def sf(text: str, name: str = "index.html") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def ids(findings):
    return [f.rule_id for f in findings]


# ------------------------------------------------------------ gradient cliché
def test_tailwind_purple_pink_gradient_flagged():
    f = run_file_rules(
        sf('<div class="bg-gradient-to-r from-purple-500 to-pink-500"></div>\n')
    )
    assert "design.gradient_cliche" in ids(f)


def test_tailwind_gradient_in_jsx_flagged():
    f = run_file_rules(
        sf(
            'export const Hero = () => (\n  <div className="bg-gradient-to-br '
            'from-indigo-500 via-purple-500 to-pink-500">hi</div>\n);\n',
            "Hero.tsx",
        )
    )
    assert "design.gradient_cliche" in ids(f)


def test_tailwind_blue_purple_gradient_flagged():
    f = run_file_rules(
        sf('<div class="bg-gradient-to-r from-blue-500 to-indigo-600"></div>\n')
    )
    assert "design.gradient_cliche" in ids(f)


def test_tailwind_arbitrary_purple_hex_flagged():
    f = run_file_rules(
        sf('<div class="bg-gradient-to-r from-[#8b5cf6] to-[#ec4899]"></div>\n')
    )
    assert "design.gradient_cliche" in ids(f)


def test_slate_gradient_not_flagged():
    f = run_file_rules(
        sf('<div class="bg-gradient-to-r from-slate-900 to-slate-700"></div>\n')
    )
    assert "design.gradient_cliche" not in ids(f)


def test_css_purple_pink_gradient_flagged():
    f = run_file_rules(
        sf(".hero { background: linear-gradient(135deg, #8b5cf6, #ec4899); }\n",
           "hero.css")
    )
    assert "design.gradient_cliche" in ids(f)


def test_css_gradient_hex_after_nested_rgb_flagged():
    """Nested rgb() must not truncate the gradient before purple/pink hex stops."""
    f = run_file_rules(
        sf(
            ".hero { background: linear-gradient(135deg, "
            "rgb(0, 0, 0), #8b5cf6, #ec4899); }\n",
            "hero.css",
        )
    )
    assert "design.gradient_cliche" in ids(f)


def test_css_gradient_purple_pink_keywords_flagged():
    f = run_file_rules(
        sf(
            ".hero { background: linear-gradient(to right, purple, pink); }\n",
            "hero.css",
        )
    )
    assert "design.gradient_cliche" in ids(f)


def test_css_blue_gradient_not_flagged():
    f = run_file_rules(
        sf(".hero { background: linear-gradient(#0ea5e9, #0369a1); }\n", "hero.css")
    )
    assert "design.gradient_cliche" not in ids(f)


# -------------------------------------------------------------- gradient text
def test_gradient_text_flagged():
    f = run_file_rules(
        sf(
            '<h1 class="bg-gradient-to-r from-purple-500 to-pink-500 '
            'bg-clip-text text-transparent">Ship faster</h1>\n'
        )
    )
    assert "design.gradient_text" in ids(f)


# ------------------------------------------------------- fabricated social proof
def test_trusted_by_stat_flagged():
    f = run_file_rules(sf("<p>Trusted by 10,000+ developers worldwide</p>\n"))
    assert "design.fake_social_proof" in ids(f)


def test_join_users_stat_flagged():
    f = run_file_rules(sf("<p>Join 50k+ happy users today</p>\n"))
    assert "design.fake_social_proof" in ids(f)


def test_review_stat_flagged():
    f = run_file_rules(sf("<p>4.9/5 from 2,000+ reviews</p>\n"))
    assert "design.fake_social_proof" in ids(f)


def test_named_customers_not_flagged():
    f = run_file_rules(sf("<p>Used by teams at Acme and Globex.</p>\n"))
    assert "design.fake_social_proof" not in ids(f)


# ------------------------------------------------------------------ emoji UI
def test_three_decorative_emoji_flagged():
    f = run_file_rules(
        sf(
            "<ul><li>\U0001f680 Fast</li><li>✨ Simple</li>"
            "<li>⚡ Light</li></ul>\n"
        )
    )
    assert ids(f).count("design.emoji_ui") == 3


def test_two_emoji_below_gate_not_flagged():
    f = run_file_rules(
        sf("<ul><li>\U0001f680 Fast</li><li>✨ Simple</li></ul>\n")
    )
    assert "design.emoji_ui" not in ids(f)


def test_emoji_in_plain_js_not_flagged():
    f = run_file_rules(
        sf(
            'const reactions = ["\U0001f680", "✨", "⚡"];\n'
            "export default reactions;\n",
            "reactions.js",
        )
    )
    assert "design.emoji_ui" not in ids(f)


# --------------------------------------------------------------- fake avatars
def test_pravatar_flagged():
    f = run_file_rules(
        sf('<img src="https://i.pravatar.cc/150?img=3" alt="user" />\n')
    )
    assert "design.fake_avatar" in ids(f)


def test_dicebear_flagged():
    f = run_file_rules(
        sf(
            'export const avatar = "https://api.dicebear.com/7.x/avataaars/svg?seed=x";\n',
            "Avatar.tsx",
        )
    )
    assert "design.fake_avatar" in ids(f)


# -------------------------------------------------------- stock illustration
def test_undraw_flagged():
    f = run_file_rules(
        sf('<img src="https://undraw.co/api/illustrations/happy.svg" alt="" />\n')
    )
    assert "design.stock_illustration" in ids(f)


# ------------------------------------------------------------ glassmorphism
def test_glassmorphism_flagged():
    f = run_file_rules(
        sf(
            '<nav class="backdrop-blur-md bg-white/10 border-white/20">'
            "menu</nav>\n"
        )
    )
    assert "design.glassmorphism" in ids(f)


def test_blur_alone_not_glass():
    f = run_file_rules(sf('<div class="backdrop-blur-sm">just blur</div>\n'))
    assert "design.glassmorphism" not in ids(f)


# -------------------------------------------------------------- landing kit
def test_landing_kit_fires_on_classic_ai_page():
    """≥3 distinct families: Inter + purple + soft radius + feature grid + CTAs."""
    text = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
<section class="hero">
  <h1 class="text-purple-600">Build faster</h1>
  <a href="#">Get Started Free</a>
  <a href="#">Learn More</a>
</section>
<section class="grid grid-cols-3 gap-8">
  <div class="rounded-2xl shadow-xl p-6">Feature A</div>
  <div class="rounded-2xl shadow-xl p-6">Feature B</div>
  <div class="rounded-3xl shadow-2xl p-6">Feature C</div>
</section>
<h2>How it works</h2>
"""
    f = run_file_rules(sf(text))
    assert "design.landing_kit" in ids(f)


def test_landing_kit_inter_alone_quiet():
    f = run_file_rules(
        sf(
            "<style>body { font-family: Inter, sans-serif; }</style>\n"
            "<p>Hello</p>\n"
        )
    )
    assert "design.landing_kit" not in ids(f)


def test_landing_kit_one_rounded_quiet():
    f = run_file_rules(
        sf('<div class="rounded-2xl p-4 bg-slate-100">card</div>\n')
    )
    assert "design.landing_kit" not in ids(f)


def test_landing_kit_two_signals_below_threshold():
    """Inter + one purple class = only 2 families — must stay quiet."""
    f = run_file_rules(
        sf(
            '<link href="https://fonts.googleapis.com/css2?family=Inter&display=swap">'
            '<button class="bg-indigo-600">Save</button>\n'
        )
    )
    assert "design.landing_kit" not in ids(f)


def test_landing_kit_weak_signals_alone_quiet():
    """Generic Tailwind marketing (radius+shadow+CTAs+grid+how-it-works) is
    human-plausible — without one strong AI signal the kit must stay quiet."""
    text = """
<section>
  <a href="/signup">Get Started Free</a>
  <a href="/docs">Learn More</a>
</section>
<h2>How it works</h2>
<section class="grid grid-cols-3 gap-8">
  <div class="rounded-2xl shadow-xl p-6">A</div>
  <div class="rounded-2xl shadow-xl p-6">B</div>
</section>
"""
    f = run_file_rules(sf(text))
    assert "design.landing_kit" not in ids(f)


def test_landing_kit_weak_plus_one_strong_fires():
    """Two weak families plus a strong one (purple accent) crosses the bar."""
    text = (
        '<a href="/go">Get started free</a> <a href="/docs">Learn more</a>\n'
        '<div class="rounded-2xl shadow-xl"></div>\n'
        '<div class="rounded-2xl shadow-xl"></div>\n'
        '<h1 class="text-purple-600">Ship</h1>\n'
    )
    f = run_file_rules(sf(text))
    assert "design.landing_kit" in ids(f)


def test_landing_kit_quiet_on_ordinary_human_pricing_page():
    """A hand-written pricing section must not read as the AI kit.

    Regression: `border-indigo-500` marking the highlighted card counted as the
    purple-accent family, and 'Most popular' + '/month' counted as the pricing
    family — both were STRONG, so this page scored 82% and 92/100 slop. Neither
    is an authorship tell: a hairline accent and the Starter/Team/Enterprise
    trio are how pricing pages have always been built.
    """
    text = """
<section class="grid grid-cols-3 gap-6">
  <div class="rounded-2xl shadow-xl p-6">
    <h3>Starter</h3><p>$9 / month</p>
    <a href="/signup">Get started free</a>
  </div>
  <div class="rounded-2xl shadow-xl p-6 border-indigo-500">
    <span>Most popular</span>
    <h3>Team</h3><p>$29 / month</p>
    <a href="/signup">Get started free</a>
  </div>
  <div class="rounded-2xl shadow-xl p-6">
    <h3>Enterprise</h3>
    <a href="/contact">Contact sales</a>
  </div>
</section>
"""
    f = run_file_rules(sf(text, "Pricing.jsx"))
    assert "design.landing_kit" not in ids(f)


def test_landing_kit_purple_paint_still_counts_over_a_bare_accent_border():
    """Purple as the paint is the tell; purple as one hairline is not."""
    weak = (
        '<a href="/go">Get started free</a> <a href="/docs">Learn more</a>\n'
        '<div class="rounded-2xl shadow-xl border-indigo-500"></div>\n'
        '<div class="rounded-2xl shadow-xl"></div>\n'
    )
    assert "design.landing_kit" not in ids(run_file_rules(sf(weak)))
    # Same page, purple moved from the border onto the headline.
    paint = weak + '<h1 class="text-purple-600">Ship</h1>\n'
    assert "design.landing_kit" in ids(run_file_rules(sf(paint)))


def test_landing_kit_pricing_alone_does_not_unlock():
    """Pricing is a convention, not a strong family — it can't carry the kit."""
    text = (
        '<div class="rounded-2xl shadow-xl"></div>\n'
        '<div class="rounded-2xl shadow-xl"></div>\n'
        '<section class="grid grid-cols-3">\n'
        "  <span>Most popular</span><p>$29 / month</p>\n"
        "  <h3>Enterprise</h3>\n"
        "</section>\n"
    )
    f = run_file_rules(sf(text))
    assert "design.landing_kit" not in ids(f)
