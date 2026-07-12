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
]
