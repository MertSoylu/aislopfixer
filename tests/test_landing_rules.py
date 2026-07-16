"""Tests for the modern landing-page tells (engine/rules/landing_tells.py)."""

from aislopfixer.engine.models import SourceFile
from aislopfixer.engine.runner import run_file_rules


def sf(text: str, name: str = "index.html") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def ids(findings):
    return [f.rule_id for f in findings]


# ------------------------------------------------------------- fake metrics
def test_metric_strip_flagged():
    """Two or more fabricated stats in one file — the classic stat strip."""
    f = run_file_rules(
        sf(
            "<div><span>99.9% uptime</span><span>24/7 support</span>"
            "<span>10k+ users</span></div>\n"
        )
    )
    assert ids(f).count("design.fake_metrics") == 3


def test_single_metric_not_flagged():
    f = run_file_rules(sf("<p>We guarantee 99.95% uptime, backed by SLA credits.</p>\n"))
    assert "design.fake_metrics" not in ids(f)


def test_nx_faster_pair_flagged():
    f = run_file_rules(
        sf("<p>Ship 10x faster.</p><p>500+ integrations out of the box.</p>\n")
    )
    assert "design.fake_metrics" in ids(f)


def test_metrics_in_js_not_flagged():
    """Stats inside plain JS code are data, not marketing copy."""
    f = run_file_rules(
        sf(
            'const stats = ["99.9% uptime", "24/7 support", "10k+ users"];\n',
            "stats.js",
        )
    )
    assert "design.fake_metrics" not in ids(f)


def test_trusted_by_count_not_double_flagged_as_metric():
    """'Trusted by 10,000+ developers' belongs to fake_social_proof, not here."""
    f = run_file_rules(
        sf("<p>Trusted by 10,000+ developers</p><p>99.9% uptime</p>\n")
    )
    assert "design.fake_metrics" not in ids(f)


# ------------------------------------------------------------ pricing triad
def test_pricing_triad_flagged():
    f = run_file_rules(
        sf(
            "<section><h3>Pro</h3><p>$29/month</p>"
            '<span class="badge">Most Popular</span>'
            "<h3>Enterprise</h3><p>Contact sales</p></section>\n"
        )
    )
    assert "design.pricing_triad" in ids(f)


def test_pricing_without_badge_not_flagged():
    f = run_file_rules(
        sf("<section><h3>Pro</h3><p>$29/month</p><h3>Enterprise</h3></section>\n")
    )
    assert "design.pricing_triad" not in ids(f)


def test_most_popular_blog_post_not_flagged():
    f = run_file_rules(
        sf("<p>Our most popular post this year covers CSS grids.</p>\n")
    )
    assert "design.pricing_triad" not in ids(f)


# ----------------------------------------------------------- section recipe
def test_html_section_recipe_flagged():
    f = run_file_rules(
        sf(
            "<!-- Hero Section -->\n<section>hi</section>\n"
            "<!-- Features Section -->\n<section>a</section>\n"
            "<!-- Pricing Section -->\n<section>b</section>\n"
            "<!-- FAQ Section -->\n<section>c</section>\n"
        )
    )
    assert "design.section_recipe" in ids(f)


def test_jsx_section_recipe_flagged():
    f = run_file_rules(
        sf(
            "export default function Page() {\n  return (\n    <main>\n"
            "      {/* Hero Section */}\n      <Hero />\n"
            "      {/* Testimonials */}\n      <Testimonials />\n"
            "      {/* Pricing */}\n      <Pricing />\n"
            "    </main>\n  );\n}\n",
            "page.tsx",
        )
    )
    assert "design.section_recipe" in ids(f)


def test_two_stock_sections_not_flagged():
    f = run_file_rules(
        sf("<!-- Hero Section -->\n<div>x</div>\n<!-- Pricing -->\n<div>y</div>\n")
    )
    assert "design.section_recipe" not in ids(f)


def test_generic_header_footer_comments_not_flagged():
    f = run_file_rules(
        sf(
            "<!-- Header -->\n<header>x</header>\n"
            "<!-- Main -->\n<main>y</main>\n"
            "<!-- Footer -->\n<footer>z</footer>\n"
        )
    )
    assert "design.section_recipe" not in ids(f)


# --------------------------------------------------------- fake logo cloud
def test_fake_logo_cloud_flagged():
    f = run_file_rules(
        sf(
            "<p>Trusted by teams at</p>\n"
            "<div><span>Google</span><span>Netflix</span>"
            "<span>Spotify</span><span>Uber</span></div>\n"
        )
    )
    assert "design.fake_logo_cloud" in ids(f)


def test_integration_list_not_flagged():
    """A real integrations list has no trust-claim lead-in."""
    f = run_file_rules(
        sf("<p>Works with Slack, Google Drive, Notion and Figma.</p>\n")
    )
    assert "design.fake_logo_cloud" not in ids(f)


def test_three_brands_not_flagged():
    f = run_file_rules(
        sf(
            "<p>Trusted by teams at</p>"
            "<div><span>Google</span><span>Netflix</span><span>Uber</span></div>\n"
        )
    )
    assert "design.fake_logo_cloud" not in ids(f)


# ---------------------------------------------------------------- blob glow
def test_blob_glow_flagged():
    f = run_file_rules(
        sf(
            '<div class="absolute -top-24 -left-24 w-96 h-96 rounded-full '
            'bg-purple-500/30 blur-3xl"></div>\n'
        )
    )
    assert "design.blob_glow" in ids(f)


def test_blob_glow_jsx_flagged():
    f = run_file_rules(
        sf(
            'export const Glow = () => (\n  <div className="pointer-events-none '
            'absolute inset-0 blur-2xl rounded-full bg-indigo-600/20" />\n);\n',
            "Glow.tsx",
        )
    )
    assert "design.blob_glow" in ids(f)


def test_rounded_avatar_not_flagged():
    f = run_file_rules(
        sf('<img class="rounded-full w-10 h-10" src="/me.png" alt="me" />\n')
    )
    assert "design.blob_glow" not in ids(f)


def test_backdrop_blur_not_blob():
    f = run_file_rules(
        sf('<div class="rounded-full backdrop-blur-3xl bg-white/10">pill</div>\n')
    )
    assert "design.blob_glow" not in ids(f)
