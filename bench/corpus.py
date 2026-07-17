"""Labeled corpus for calibration.

Each case is a single source snippet with a ground-truth label:

* ``expect`` — rule-id prefixes that *should* fire (slop cases). A case passes
  recall if every prefix is matched by at least one finding.
* ``clean=True`` — the snippet is legitimate; *any* finding is a false positive.

Clean cases double as guards for the code-aware masking: ``eval`` in a comment
or a string, ``process.env`` secrets and static SQL must stay silent.
"""

from __future__ import annotations

CASES: list[dict] = [
    # ---------------------------------------------------------------- slop cases
    {
        "name": "ai_leak_strong_in_html",
        "filename": "about.html",
        "text": "<p>As an AI language model, I cannot provide medical advice.</p>\n",
        "expect": {"ai_leak.strong"},
    },
    {
        "name": "ai_leak_in_code_comment",
        "filename": "util.js",
        "text": "// As an AI language model, I should note this is a stub.\n"
                "export const x = 1;\n",
        "expect": {"ai_leak.strong"},
    },
    {
        "name": "codegen_elision",
        "filename": "app.js",
        "text": "function init() {\n  // ... rest of the implementation ...\n}\n",
        "expect": {"codegen.elision"},
    },
    {
        "name": "codegen_debugger",
        "filename": "app.js",
        "text": "function f() {\n  debugger;\n  return 1;\n}\n",
        "expect": {"codegen.debugger"},
    },
    {
        "name": "merge_conflict",
        "filename": "config.js",
        "text": "const port =\n<<<<<<< HEAD\n  3000;\n=======\n  8080;\n>>>>>>> feat\n",
        "expect": {"merge.conflict_marker"},
    },
    {
        "name": "security_eval",
        "filename": "handler.js",
        "text": "function run(src) {\n  return eval(src);\n}\n",
        "expect": {"security.eval"},
    },
    {
        "name": "security_eval_in_template_hole",
        "filename": "handler.js",
        "text": "const x = `ok ${eval(userInput)}`;\n",
        "expect": {"security.eval"},
    },
    {
        "name": "ai_leak_in_vue_script",
        "filename": "Widget.vue",
        "text": (
            "<template><p>hi</p></template>\n"
            "<script setup>\n"
            "// As an AI language model, this is a stub.\n"
            "export const x = 1;\n"
            "</script>\n"
        ),
        "expect": {"ai_leak.strong"},
    },
    {
        "name": "security_sqli_template",
        "filename": "db.js",
        "text": "const q = `SELECT * FROM users WHERE id = ${userId}`;\n",
        "expect": {"security.sqli"},
    },
    {
        "name": "secret_placeholder",
        "filename": "config.js",
        "text": 'const apiKey = "YOUR_API_KEY_HERE";\n',
        "expect": {"secret"},
    },
    {
        "name": "secret_high_entropy",
        "filename": "config.js",
        "text": 'const token = "aZ3kL9qXr2mP7wVt1nB4cE6dF8gH0jK";\n',
        "expect": {"security.high_entropy_secret"},
    },
    {
        "name": "buzzword_density",
        "filename": "landing.html",
        "text": "<p>We leverage cutting-edge synergy to revolutionize seamless "
                "world-class solutions.</p>\n",
        "expect": {"buzzword"},
    },
    {
        "name": "codegen_empty_catch",
        "filename": "api.js",
        "text": "async function load() {\n  try {\n    return await fetchData();\n"
                "  } catch (e) {}\n}\n",
        "expect": {"codegen.empty_catch"},
    },
    {
        "name": "security_token_in_storage",
        "filename": "auth.js",
        "text": "localStorage.setItem('accessToken', data.token);\n",
        "expect": {"security.token_in_storage"},
    },
    {
        "name": "security_postmessage_wildcard",
        "filename": "embed.js",
        "text": "window.parent.postMessage({ user }, '*');\n",
        "expect": {"security.postmessage_wildcard"},
    },
    {
        "name": "prose_not_just_contrast",
        "filename": "landing.html",
        "text": "<p>This is not just a template — it's a complete design system.</p>\n",
        "expect": {"prose.not_just_contrast"},
    },
    {
        "name": "unused_import",
        "filename": "page.ts",
        "text": "import { render, hydrate } from './dom';\nrender(app);\n",
        "expect": {"import.unused"},
    },
    {
        "name": "fake_api_url",
        "filename": "client.js",
        "text": "const res = await fetch('https://api.yourdomain.com/v1/data');\n",
        "expect": {"placeholder.fake_api"},
    },
    {
        "name": "catch_return_default",
        "filename": "parse.js",
        "text": "function safeParse(s) {\n  try {\n    return JSON.parse(s);\n"
                "  } catch (e) {\n    return null;\n  }\n}\n",
        "expect": {"codegen.catch_return_default"},
    },
    {
        "name": "log_only_catch",
        "filename": "load.js",
        "text": "init().catch(err => console.error(err));\n",
        "expect": {"codegen.log_only_catch"},
    },
    # --------------------------------------------------------------- clean cases
    {
        "name": "clean_plain_js",
        "filename": "list.js",
        "text": "const active = data.filter((x) => x.active);\n",
        "clean": True,
    },
    {
        "name": "clean_empty_catch_with_comment",
        "filename": "prefs.js",
        "text": "function readPrefs() {\n  try {\n    return JSON.parse(localStorage.getItem('prefs'));\n"
                "  } catch (err) {\n    // ignore: private mode / quota — defaults are fine\n  }\n"
                "  return {};\n}\n",
        "clean": True,
    },
    {
        "name": "clean_eval_in_comment",
        "filename": "note.js",
        "text": "// never call eval() on user input; use JSON.parse instead\n"
                "const v = JSON.parse(raw);\n",
        "clean": True,
    },
    {
        "name": "clean_eval_in_string",
        "filename": "msg.js",
        "text": 'const help = "the eval() function is dangerous";\n',
        "clean": True,
    },
    {
        "name": "clean_eval_in_template_static",
        "filename": "msg.js",
        "text": "const help = `the eval() function is dangerous`;\n",
        "clean": True,
    },
    {
        "name": "clean_static_sql",
        "filename": "q.js",
        "text": 'const sql = "SELECT name FROM users";\n',
        "clean": True,
    },
    {
        "name": "clean_textcontent",
        "filename": "dom.js",
        "text": "el.textContent = userInput;\n",
        "clean": True,
    },
    {
        "name": "clean_env_secret",
        "filename": "env.js",
        "text": "const apiKey = process.env.API_KEY;\n",
        "clean": True,
    },
    {
        "name": "clean_crypto_random",
        "filename": "id.js",
        "text": "const id = crypto.randomUUID();\n",
        "clean": True,
    },
    {
        "name": "clean_handled_catch",
        "filename": "load.js",
        "text": "try {\n  run();\n} catch (err) {\n  logger.error(err);\n}\n",
        "clean": True,
    },
    {
        "name": "clean_theme_in_storage",
        "filename": "prefs.js",
        "text": "localStorage.setItem('theme', mode);\n",
        "clean": True,
    },
    {
        "name": "clean_postmessage_exact_origin",
        "filename": "frame.js",
        "text": "frame.contentWindow.postMessage(msg, 'https://app.example.com');\n",
        "clean": True,
    },
    {
        "name": "clean_used_imports",
        "filename": "view.tsx",
        "text": "import React from 'react';\nimport { List } from './List';\n"
                "export const View = () => <List />;\n",
        "clean": True,
    },
    {
        "name": "clean_catch_variable_fallback",
        "filename": "cache.js",
        "text": "function get(k) {\n  try {\n    return fresh(k);\n"
                "  } catch (e) {\n    return cache[k];\n  }\n}\n",
        "clean": True,
    },
    {
        "name": "clean_real_api_url",
        "filename": "pay.js",
        "text": "const res = await fetch('https://api.stripe.com/v1/charges');\n",
        "clean": True,
    },
    {
        "name": "clean_plain_prose",
        "filename": "home.html",
        "text": "<p>We build accounting software for independent dentists.</p>\n",
        "clean": True,
    },
    {
        "name": "design_slop_hero",
        "filename": "index.html",
        "text": '<section class="bg-gradient-to-r from-purple-500 via-pink-500 '
                'to-pink-400">\n<h1>Ship faster</h1>\n'
                "<p>Trusted by 10,000+ developers</p>\n"
                "<ul><li>\U0001f680 Fast</li><li>✨ Simple</li>"
                "<li>⚡ Light</li></ul>\n</section>\n",
        "expect": {
            "design.gradient_cliche",
            "design.fake_social_proof",
            "design.emoji_ui",
        },
    },
    {
        "name": "design_css_gradient",
        "filename": "hero.css",
        "text": ".hero {\n  background: linear-gradient(135deg, #8b5cf6 0%, "
                "#ec4899 100%);\n}\n",
        "expect": {"design.gradient_cliche"},
    },
    {
        "name": "clean_brand_gradient",
        "filename": "banner.html",
        "text": '<div class="bg-gradient-to-r from-slate-900 to-slate-700">'
                "Quarterly report</div>\n",
        "clean": True,
    },
    {
        "name": "clean_blue_css_gradient",
        "filename": "theme.css",
        "text": ".header {\n  background: linear-gradient(#0ea5e9, #0369a1);\n}\n",
        "clean": True,
    },
    {
        "name": "clean_single_emoji_copy",
        "filename": "hi.html",
        "text": "<h1>Welcome \U0001f44b</h1><p>Sign in to continue.</p>\n",
        "clean": True,
    },
    {
        "name": "design_landing_kit",
        "filename": "landing.html",
        "text": (
            '<link href="https://fonts.googleapis.com/css2?family=Inter&display=swap">\n'
            '<h1 class="text-purple-600">Build faster</h1>\n'
            '<a href="#">Get Started Free</a><a href="#">Learn More</a>\n'
            '<section class="grid grid-cols-3 gap-8">\n'
            '  <div class="rounded-2xl shadow-xl">A</div>\n'
            '  <div class="rounded-2xl shadow-xl">B</div>\n'
            '  <div class="rounded-3xl shadow-2xl">C</div>\n'
            "</section>\n"
            "<h2>How it works</h2>\n"
        ),
        "expect": {"design.landing_kit"},
    },
    {
        "name": "design_fake_avatar",
        "filename": "testimonial.html",
        "text": '<img src="https://i.pravatar.cc/150?img=12" alt="customer" />\n',
        "expect": {"design.fake_avatar"},
    },
    {
        "name": "design_glass_nav",
        "filename": "nav.html",
        "text": '<nav class="backdrop-blur-md bg-white/10 border-white/20">Nav</nav>\n',
        "expect": {"design.glassmorphism"},
    },
    {
        "name": "clean_inter_alone",
        "filename": "typography.html",
        "text": "<style>body { font-family: Inter, system-ui, sans-serif; }</style>\n"
                "<p>Hello</p>\n",
        "clean": True,
    },
    {
        # A hand-written pricing section: soft radii, shadows, a 3-col grid, two
        # CTAs, an indigo hairline on the highlighted card and the universal
        # Starter/Team/Enterprise trio. Every one of those is how pricing pages
        # have always been built — none is an authorship tell, and the kit used
        # to score this page 82%.
        "name": "clean_human_pricing_page",
        "filename": "Pricing.jsx",
        "text": '<section className="grid grid-cols-3 gap-6">\n'
                '  <div className="rounded-2xl shadow-xl p-6">\n'
                "    <h3>Starter</h3><p>$9 / month</p>\n"
                '    <a href="/signup">Get started free</a>\n'
                "  </div>\n"
                '  <div className="rounded-2xl shadow-xl p-6 border-indigo-500">\n'
                "    <span>Most popular</span>\n"
                "    <h3>Team</h3><p>$29 / month</p>\n"
                '    <a href="/signup">Get started free</a>\n'
                "  </div>\n"
                '  <div className="rounded-2xl shadow-xl p-6">\n'
                "    <h3>Enterprise</h3>\n"
                '    <a href="/contact">Contact sales</a>\n'
                "  </div>\n"
                "</section>\n",
        "clean": True,
    },
    # ------------------------------------------- modern landing/copy slop cases
    {
        "name": "fake_metric_strip",
        "filename": "stats.html",
        "text": "<div><span>99.9% uptime</span><span>24/7 support</span>"
                "<span>10k+ users</span></div>\n",
        "expect": {"design.fake_metrics"},
    },
    {
        # The triad only means something next to another tell — here a strip of
        # invented stats. Its clean twin is `clean_bare_pricing_triad` below:
        # the two differ by exactly the corroborating signal.
        "name": "pricing_triad",
        "filename": "pricing.html",
        "text": "<section><p>99.9% uptime and 10k+ users</p>"
                "<h3>Pro</h3><p>$29/month</p>"
                '<span class="badge">Most Popular</span>'
                "<h3>Enterprise</h3><p>Contact sales</p></section>\n",
        "expect": {"design.pricing_triad"},
    },
    {
        # Ground truth, corrected: a bare Starter/Pro/Enterprise card with a
        # "Most Popular" badge and per-month pricing is how Stripe, Linear and
        # every other real pricing page is built. Labelling it slop made the
        # rule fire on ~every genuine pricing page.
        "name": "clean_bare_pricing_triad",
        "filename": "pricing.html",
        "text": "<section><h3>Pro</h3><p>$29/month</p>"
                '<span class="badge">Most Popular</span>'
                "<h3>Enterprise</h3><p>Contact sales</p></section>\n",
        "clean": True,
    },
    {
        "name": "section_recipe",
        "filename": "page.tsx",
        "text": "export default function Page() {\n  return (\n    <main>\n"
                "      {/* Hero Section */}\n      <Hero />\n"
                "      {/* Testimonials */}\n      <Testimonials />\n"
                "      {/* Pricing */}\n      <Pricing />\n"
                "    </main>\n  );\n}\n",
        "expect": {"design.section_recipe"},
    },
    {
        "name": "fake_logo_cloud",
        "filename": "logos.html",
        "text": "<p>Trusted by teams at</p>\n"
                "<div><span>Google</span><span>Netflix</span>"
                "<span>Spotify</span><span>Uber</span></div>\n",
        "expect": {"design.fake_logo_cloud"},
    },
    {
        "name": "blob_glow_decor",
        "filename": "hero.html",
        "text": '<div class="absolute -top-24 -left-24 w-96 h-96 rounded-full '
                'bg-purple-500/30 blur-3xl"></div>\n',
        "expect": {"design.blob_glow"},
    },
    {
        "name": "generic_microcopy_pair",
        "filename": "cta.html",
        "text": "<p>No credit card required. Cancel anytime.</p>\n",
        "expect": {"copy.microcopy"},
    },
    {
        "name": "template_testimonial",
        "filename": "quotes.html",
        "text": "<blockquote>This tool has completely transformed the way we "
                "work.</blockquote>\n",
        "expect": {"copy.testimonial"},
    },
    # ------------------------------------------ modern landing/copy clean guards
    {
        "name": "clean_single_metric",
        "filename": "sla.html",
        "text": "<p>We guarantee 99.95% uptime, backed by SLA credits.</p>\n",
        "clean": True,
    },
    {
        "name": "clean_pricing_no_badge",
        "filename": "plans.html",
        "text": "<section><h3>Pro</h3><p>$29/month</p>"
                "<h3>Enterprise</h3><p>Contact sales</p></section>\n",
        "clean": True,
    },
    {
        "name": "clean_header_footer_comments",
        "filename": "layout.html",
        "text": "<!-- Header -->\n<header>x</header>\n"
                "<!-- Main -->\n<main>y</main>\n"
                "<!-- Footer -->\n<footer>z</footer>\n",
        "clean": True,
    },
    {
        "name": "clean_integration_list",
        "filename": "integrations.html",
        "text": "<p>Works with Slack, Google Drive, Notion and Figma.</p>\n",
        "clean": True,
    },
    {
        "name": "clean_rounded_avatar",
        "filename": "team.html",
        "text": '<img class="rounded-full w-10 h-10" src="/mert.png" alt="Mert" />\n',
        "clean": True,
    },
    {
        "name": "clean_single_microcopy",
        "filename": "billing.html",
        "text": "<p>Cancel anytime from your account settings.</p>\n",
        "clean": True,
    },
    {
        "name": "clean_specific_testimonial",
        "filename": "case-study.html",
        "text": "<blockquote>Migrating our invoicing to Billfold cut month-end "
                "close from 4 days to 6 hours.</blockquote>\n",
        "clean": True,
    },
    {
        # Human-made Tailwind marketing page: soft radii, shadows, dual CTAs,
        # a 3-col grid and a "How it works" heading — all weak, human-plausible
        # signals. Without one strong AI tell the landing-kit rule must not fire.
        "name": "clean_human_tailwind_marketing",
        "filename": "landing.html",
        "text": '<section class="grid grid-cols-3 gap-8">\n'
                '  <div class="rounded-2xl shadow-xl p-6">Starter</div>\n'
                '  <div class="rounded-2xl shadow-xl p-6">Team</div>\n'
                '</section>\n'
                '<a href="/signup">Get started free</a>\n'
                '<a href="/features">Learn more</a>\n'
                '<h2>How it works</h2>\n',
        "clean": True,
    },
    {
        # Hand-written shop page: a sticky blurred header and two rounded cards
        # with hairline borders. No purple, no CTA, no hero, no metrics. The
        # glass family had no proximity gate and counted `border-white/10` as a
        # translucent surface, so the blur + a hairline unlocked a _KIT_STRONG
        # family and this scored 82% design.landing_kit / 89 slop.
        "name": "clean_human_blurred_header_shop",
        "filename": "shop.html",
        "text": '<header class="sticky top-0 z-40 border-b border-white/10 '
                'backdrop-blur">\n'
                '  <nav class="flex gap-6 px-6 py-4"><a href="/beans">Beans</a>'
                '<a href="/visit">Visit</a></nav>\n'
                '</header>\n'
                '<main class="px-6 py-10">\n'
                '  <h1 class="text-3xl font-semibold">Bristol-roasted coffee '
                'since 1998</h1>\n'
                '  <div class="rounded-2xl border border-white/10 p-6 shadow-xl">\n'
                '    <h2>Ethiopia Guji</h2><p>Washed, roasted for filter. 250g.</p>\n'
                '  </div>\n'
                '  <div class="rounded-2xl border border-white/10 p-6 shadow-xl">\n'
                '    <h2>Brazil Cerrado</h2><p>Natural, for espresso. 250g.</p>\n'
                '  </div>\n'
                '</main>\n',
        "clean": True,
    },
    {
        # The two _CSS_GRADIENT lookaheads scan from the same offset, so while
        # `violet` sat in both colour lists a single stop satisfied both halves
        # and a rainbow was reported as a two-stop "purple→pink" gradient.
        "name": "clean_rainbow_gradient",
        "filename": "brand.css",
        "text": ".sunset { background: linear-gradient(to right, violet, orange); }\n"
                ".rainbow { background: linear-gradient(to right, violet, indigo, "
                "blue, green, yellow, orange, red); }\n"
                ".fade { background: linear-gradient(90deg, #8b5cf6, #0f172a); }\n",
        "clean": True,
    },
    {
        # `<token>` is how every CLI documents a required argument, not a leaked
        # credential — this drew three 85%-confidence RISKY "rotate this
        # credential" findings over a usage string.
        "name": "clean_cli_usage_docs",
        "filename": "cli.md",
        "text": "# mycli reference\n\n## Authentication\n\n"
                "    mycli auth login <token>\n\n"
                "Pass it as `<token>`; the client stores it in the OS keychain.\n\n"
                "    mycli deploy <key> --region eu-west-2\n",
        "clean": True,
    },
    {
        # `catch { return false; }` with no error binding is a capability probe
        # — the correct implementation of feature detection, and the shape
        # _EMPTY_CATCH already exempts when a comment documents it.
        "name": "clean_feature_detection_probe",
        "filename": "storage.ts",
        "text": "// Safari in private mode throws on any write.\n"
                "export function hasLocalStorage(): boolean {\n"
                '  try {\n    window.localStorage.setItem("__probe__", "1");\n'
                '    window.localStorage.removeItem("__probe__");\n'
                "    return true;\n  }\n"
                "  catch { return false; }\n}\n",
        "clean": True,
    },
    {
        # Prose *about* lorem ipsum is not lorem ipsum. The `[^<>\n]*` tail only
        # stops at a tag, so in Markdown the AUTO fix ate the rest of the line.
        "name": "clean_prose_about_lorem",
        "filename": "design-notes.md",
        "text": "Our designers keep shipping comps with lorem ipsum in the body "
                "slots, and stakeholders read it as final copy.\n\n"
                "Decision: lorem ipsum is banned in any comp that goes to a "
                "client. Use real copy from the CMS export instead.\n",
        "clean": True,
    },
]
