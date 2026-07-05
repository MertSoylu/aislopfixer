"""Tests for the AI-mistake rules: merge conflicts, hedge comments, secrets."""

from aislopfixer.engine.models import Category, Fixability, Severity, SourceFile
from aislopfixer.engine.runner import run_file_rules


def sf(text: str, name: str = "app.js") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def _ids(findings, prefix):
    return [f for f in findings if f.rule_id.startswith(prefix)]


# ----------------------------------------------------------- merge conflicts
def test_merge_conflict_full_block_flagged():
    text = (
        "const port =\n"
        "<<<<<<< HEAD\n"
        "  3000;\n"
        "=======\n"
        "  8080;\n"
        ">>>>>>> feature/config\n"
    )
    f = _ids(run_file_rules(sf(text)), "merge.conflict_marker")
    assert len(f) == 3  # open, divider, close
    assert all(x.severity is Severity.ERROR for x in f)
    assert all(x.fixability is Fixability.MANUAL for x in f)


def test_merge_conflict_diff3_base_marker():
    text = (
        "<<<<<<< ours\n a\n||||||| base\n b\n=======\n c\n>>>>>>> theirs\n"
    )
    f = _ids(run_file_rules(sf(text)), "merge.conflict_marker")
    assert len(f) == 4  # open, base, divider, close


def test_bare_equals_line_not_flagged_without_conflict():
    # A setext underline / comment rule of seven '=' is NOT a conflict on its own.
    text = "Title\n=======\n\nbody text here\n"
    f = _ids(run_file_rules(sf(text, "doc.md")), "merge.conflict_marker")
    assert not f


def test_equals_divider_wrong_width_not_flagged():
    text = "<<<<<<< HEAD\na\n========\nb\n>>>>>>> x\n"  # 8 '=' is not a marker
    f = [x for x in _ids(run_file_rules(sf(text)), "merge.conflict_marker")
         if "=======" in x.message]
    assert not f


def test_shift_operator_not_flagged():
    text = "const mask = 1 << 7;\nconst y = a >> 7;\n"
    f = _ids(run_file_rules(sf(text)), "merge.conflict_marker")
    assert not f


# -------------------------------------------------------- security: XSS sinks
def test_xss_innerhtml_dynamic_flagged():
    f = _ids(run_file_rules(sf("el.innerHTML = userInput;\n")), "security.xss_innerhtml")
    assert f and f[0].category is Category.SECURITY


def test_xss_innerhtml_template_flagged():
    f = _ids(run_file_rules(sf("node.innerHTML = `<b>${name}</b>`;\n")), "security.xss_innerhtml")
    assert f


def test_xss_innerhtml_static_string_not_flagged():
    # A constant string assignment is not the dynamic-injection smell.
    assert not _ids(run_file_rules(sf('el.innerHTML = "<b>hello</b>";\n')), "security.xss_innerhtml")


def test_xss_dangerously_set_inner_html():
    text = "export default () => <div dangerouslySetInnerHTML={{__html: body}} />;\n"
    assert _ids(run_file_rules(sf(text, "Page.tsx")), "security.xss_dangerously_set")


def test_xss_v_html_flagged():
    assert _ids(run_file_rules(sf('<div v-html="msg"></div>\n', "App.vue")), "security.xss_v_html")


def test_document_write_flagged():
    assert _ids(run_file_rules(sf("document.write(location.hash);\n")), "security.xss_document_write")


# --------------------------------------------------- security: code injection
def test_eval_flagged_error():
    f = _ids(run_file_rules(sf("const r = eval(payload);\n")), "security.eval")
    assert f and f[0].severity is Severity.ERROR


def test_eval_not_flagged_in_identifier():
    # 'retrieval' contains 'eval' but is not an eval() call.
    assert not _ids(run_file_rules(sf("const x = retrieval();\n")), "security.eval")


def test_string_timer_flagged():
    assert _ids(run_file_rules(sf('setTimeout("doThing()", 100);\n')), "security.string_timer")


def test_function_call_timer_not_flagged():
    assert not _ids(run_file_rules(sf("setTimeout(doThing, 100);\n")), "security.string_timer")


# ----------------------------------------------------- security: SQL injection
def test_sqli_template_literal():
    text = "db.query(`SELECT * FROM users WHERE id = ${req.params.id}`);\n"
    f = _ids(run_file_rules(sf(text)), "security.sqli")
    assert f and f[0].severity is Severity.ERROR


def test_sqli_string_concat():
    text = 'db.query("SELECT * FROM users WHERE name = " + name);\n'
    assert _ids(run_file_rules(sf(text)), "security.sqli")


def test_parameterized_query_not_flagged():
    text = 'db.query("SELECT * FROM users WHERE id = ?", [id]);\n'
    assert not _ids(run_file_rules(sf(text)), "security.sqli")


# ------------------------------------------------- security: command injection
def test_command_injection_template():
    text = "exec(`rm -rf ${dir}`);\n"
    assert _ids(run_file_rules(sf(text)), "security.command_injection")


def test_exec_static_command_not_flagged():
    assert not _ids(run_file_rules(sf('exec("ls -la");\n')), "security.command_injection")


# ---------------------------------------------------- security: TLS / CORS / crypto
def test_tls_verification_disabled():
    text = "const agent = new https.Agent({ rejectUnauthorized: false });\n"
    f = _ids(run_file_rules(sf(text)), "security.tls_disabled")
    assert f and f[0].severity is Severity.ERROR


def test_cors_wildcard_flagged():
    assert _ids(run_file_rules(sf("app.use(cors({ origin: '*' }));\n")), "security.cors_wildcard")


def test_weak_md5_hash_flagged():
    assert _ids(run_file_rules(sf('crypto.createHash("md5").update(p);\n')), "security.weak_hash")


def test_insecure_random_for_token_flagged():
    text = "const token = Math.random().toString(36);\n"
    assert _ids(run_file_rules(sf(text)), "security.insecure_random")


def test_insecure_random_non_secret_not_flagged():
    # Math.random() for a UI animation offset is fine — no secret context.
    text = "const offset = Math.random() * 10;\n"
    assert not _ids(run_file_rules(sf(text)), "security.insecure_random")


# ------------------------------------------------ security: hardcoded secrets
def test_hardcoded_aws_key():
    assert _ids(run_file_rules(sf('const k = "AKIAIOSFODNN7EXAMPLE";\n')), "security.hardcoded_secret")


def test_hardcoded_github_token():
    tok = "ghp_" + "a" * 36
    assert _ids(run_file_rules(sf(f'const t = "{tok}";\n')), "security.hardcoded_secret")


def test_hardcoded_private_key_block():
    text = "const key = `-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n`;\n"
    f = _ids(run_file_rules(sf(text)), "security.hardcoded_secret")
    assert f and f[0].severity is Severity.ERROR


def test_random_env_var_name_not_a_secret():
    assert not _ids(run_file_rules(sf("const key = process.env.API_KEY;\n")), "security.hardcoded_secret")


# ----------------------------------------------- copy-paste markdown fence
def test_markdown_fence_in_js_flagged():
    text = "```javascript\nconst x = 1;\n```\n"
    f = _ids(run_file_rules(sf(text, "app.js")), "codegen.markdown_fence")
    assert f and f[0].severity is Severity.ERROR


def test_markdown_fence_not_flagged_in_markdown_file():
    # In an actual .md file a fence is legitimate content.
    text = "```javascript\nconst x = 1;\n```\n"
    assert not _ids(run_file_rules(sf(text, "doc.md")), "codegen.markdown_fence")


# -------------------------------------------------------------------- secrets
def test_secret_placeholder_token():
    f = _ids(run_file_rules(sf('const k = "YOUR_API_KEY_HERE";\n')), "secret.")
    assert f and f[0].category is Category.PLACEHOLDER


def test_secret_lowercase_kebab_token():
    assert _ids(run_file_rules(sf('fetch(url, {headers: {auth: "your-token"}});\n')), "secret.")


def test_secret_angle_bracket_token():
    assert _ids(run_file_rules(sf('Authorization: "<your-secret>"\n')), "secret.")


def test_secret_fake_provider_key():
    f = _ids(run_file_rules(sf('OPENAI = "sk-xxxxxxxxxxxxxxxx"\n')), "secret.fake_key")
    assert f


def test_secret_assignment_changeme():
    f = _ids(run_file_rules(sf('password = "changeme"\n')), "secret.assignment")
    assert f


def test_secret_env_read_not_flagged():
    # Reading from the environment is the CORRECT pattern — never a placeholder.
    text = "const apiKey = process.env.API_KEY;\nconst t = import.meta.env.VITE_TOKEN;\n"
    assert not _ids(run_file_rules(sf(text)), "secret.")


def test_secret_real_looking_value_not_flagged():
    # A value that is not an obvious placeholder is out of scope for this rule.
    text = 'const token = "a8f3kd92ldk20fj23";\n'
    assert not _ids(run_file_rules(sf(text)), "secret.assignment")


def test_secret_change_password_prose_not_flagged():
    # Natural prose "Change Password" (space-separated) is a UI label, not a token.
    text = "<button>Change Password</button>\n"
    assert not _ids(run_file_rules(sf(text, "index.html")), "secret.")
