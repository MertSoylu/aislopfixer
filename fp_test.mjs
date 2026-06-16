const re = /^[ \t]*debugger\s*;?\s*$/m;

const cases = [
  // [label, content]
  ["POS:    debugger;", "    debugger;"],
  ["POS: debugger", "debugger"],
  ["POS:   debugger ;", "  debugger ;"],

  ["NEG: const debugger_enabled", "const debugger_enabled = true;"],
  ["NEG: // debugger;", "// debugger;"],
  ["NEG: if (debug) debugger;", "if (debug) debugger;"],
  ["NEG: logger.debug attached", "logger.debug('debugger attached');"],

  // ---- ADVERSARIAL CANDIDATES ----

  // 1. Markdown prose / docs listing the keyword as a value or word on its own line
  ["MD list item bare word", "- debugger\n- console\n- profiler"],
  ["MD heading-ish", "debugger\n========"],

  // 2. CSS / config: a value named debugger on its own line
  ["YAML key/scalar", "tools:\n  debugger\n  linter"],

  // 3. A devtools protocol / API string array, one per line in source
  ["JS array element bare", "const domains = [\n  debugger,\n  network\n];"],

  // 4. Template literal containing example code (docs site)
  ["template literal code sample", "const code = `\nfunction f() {\n  debugger;\n}\n`;"],

  // 5. Markdown fenced code block teaching about debugger statement
  ["MD fenced code teaching", "```js\nfunction f() {\n  debugger;\n}\n```"],

  // 6. Comment block JSDoc line that is just the word (rare)
  ["block comment line", "/*\n  debugger;\n*/"],

  // 7. CLI help text / package.json script value isn't line-anchored alone but:
  ["shell heredoc word", "node --inspect-brk\ndebugger\n"],

  // 8. A Chrome DevTools "Debugger" domain in a string list (TS union split)
  ["TS string literal own line", "type T =\n  | 'network'\n  | 'debugger'\n  | 'console';"],

  // 9. Python? (web projects sometimes have .py) pdb has no 'debugger' but:
  // skip

  // 10. Markdown table cell? no, line anchored both ends.

  // 11. A variable assignment spanning: `const x =\n  debugger\n` (not valid)
  // 12. Object key shorthand on own line
  ["object shorthand key", "const obj = {\n  debugger\n};"],
];

for (const [label, content] of cases) {
  const m = re.test(content);
  console.log((m ? "MATCH  " : "no     ") + "| " + label);
}
