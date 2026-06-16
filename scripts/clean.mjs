// Remove Python build artifacts before packing/publishing the npm tarball.
// npm does not reliably honor .npmignore for files inside a `files`-allowlisted
// directory, so we strip them physically here. Runs via the `prepack` script.

import { readdirSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");

function walk(dir) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === "__pycache__" || e.name.endsWith(".egg-info")) {
        rmSync(p, { recursive: true, force: true });
        console.log(`removed ${p}`);
        continue;
      }
      walk(p);
    } else if (e.name.endsWith(".pyc") || e.name.endsWith(".pyo")) {
      rmSync(p, { force: true });
    }
  }
}

try {
  statSync(join(ROOT, "src"));
  walk(join(ROOT, "src"));
} catch {
  // nothing to clean
}
