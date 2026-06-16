#!/usr/bin/env node
"use strict";

/**
 * npm launcher for aislopfixer (a Python / Textual TUI).
 *
 * Strategy: find a Python >= 3.11 on the host, create a private virtualenv in
 * the user's home dir on first run, pip-install the bundled Python package
 * (which pulls in `textual`), then exec the TUI with the user's args.
 *
 * The venv is keyed by package version so upgrades rebuild cleanly. After the
 * first run everything is cached and startup is instant.
 */

const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const IS_WINDOWS = process.platform === "win32";
const PKG_ROOT = path.resolve(__dirname, "..");
const PKG_VERSION = require(path.join(PKG_ROOT, "package.json")).version;
const MIN_PY = [3, 11];

const HOME_DIR = path.join(os.homedir(), ".aislopfixer");
const VENV_DIR = path.join(HOME_DIR, `venv-${PKG_VERSION}`);
const READY_MARKER = path.join(VENV_DIR, ".ready");

function log(msg) {
  process.stderr.write(`aislopfixer: ${msg}\n`);
}

function fail(msg) {
  process.stderr.write(`\naislopfixer: ${msg}\n`);
  process.exit(1);
}

/** Return python version [major, minor] for a launcher command, or null. */
function pythonVersion(cmd, extraArgs) {
  const args = (extraArgs || []).concat([
    "-c",
    "import sys;print('%d.%d' % sys.version_info[:2])",
  ]);
  const res = spawnSync(cmd, args, { encoding: "utf8" });
  if (res.status !== 0 || !res.stdout) return null;
  const m = res.stdout.trim().match(/^(\d+)\.(\d+)$/);
  if (!m) return null;
  return [parseInt(m[1], 10), parseInt(m[2], 10)];
}

function meetsMin(ver) {
  if (!ver) return false;
  if (ver[0] !== MIN_PY[0]) return ver[0] > MIN_PY[0];
  return ver[1] >= MIN_PY[1];
}

/** Locate a usable host python, returning { cmd, args }. */
function findHostPython() {
  const candidates = [
    { cmd: "python3", args: [] },
    { cmd: "python", args: [] },
  ];
  if (IS_WINDOWS) candidates.push({ cmd: "py", args: ["-3"] });

  for (const c of candidates) {
    const ver = pythonVersion(c.cmd, c.args);
    if (meetsMin(ver)) return c;
  }
  return null;
}

/** Path to the python executable inside the venv. */
function venvPython() {
  return IS_WINDOWS
    ? path.join(VENV_DIR, "Scripts", "python.exe")
    : path.join(VENV_DIR, "bin", "python");
}

function run(cmd, args, opts) {
  const res = spawnSync(cmd, args, Object.assign({ stdio: "inherit" }, opts || {}));
  if (res.error) fail(`failed to run ${cmd}: ${res.error.message}`);
  return res.status === null ? 1 : res.status;
}

function ensureVenv() {
  if (fs.existsSync(READY_MARKER) && fs.existsSync(venvPython())) return;

  const host = findHostPython();
  if (!host) {
    fail(
      "no suitable Python found. aislopfixer needs Python >= 3.11.\n" +
        "Install it from https://www.python.org/downloads/ and try again."
    );
  }

  log("first run — setting up an isolated Python environment (one time)...");

  // Clean any half-built venv from a previous interrupted run.
  if (fs.existsSync(VENV_DIR)) {
    fs.rmSync(VENV_DIR, { recursive: true, force: true });
  }
  fs.mkdirSync(HOME_DIR, { recursive: true });

  let code = run(host.cmd, host.args.concat(["-m", "venv", VENV_DIR]));
  if (code !== 0) fail("could not create the Python virtualenv.");

  const py = venvPython();
  log("installing dependencies (textual)... this needs internet the first time.");

  code = run(py, ["-m", "pip", "install", "--upgrade", "pip", "--quiet"]);
  if (code !== 0) log("warning: pip self-upgrade failed; continuing.");

  code = run(py, ["-m", "pip", "install", "--quiet", PKG_ROOT]);
  if (code !== 0) {
    fs.rmSync(VENV_DIR, { recursive: true, force: true });
    fail("failed to install the Python package. Check your internet connection.");
  }

  fs.writeFileSync(READY_MARKER, `${PKG_VERSION}\n`);
  log("setup complete.");
}

function main() {
  ensureVenv();
  const code = run(venvPython(), ["-m", "aislopfixer"].concat(process.argv.slice(2)));
  process.exit(code);
}

main();
