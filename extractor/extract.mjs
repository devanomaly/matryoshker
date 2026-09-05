#!/usr/bin/env node
/**
 * extract.mjs — single-command CLI wrapper for the deterministic
 * structural extraction (phase 1), derived from Understand-Anything.
 *
 * Usage:
 *   node extract.mjs <repoRoot> --out <dir> [--exclude "pattern1,pattern2"] [--lang <language>]
 *
 * Flow:
 *   a) scan-project.mjs <repoRoot> <out>/scan-output.json [--exclude ...]
 *   b) build <out>/im-input.json from the scan (filtered by --lang, if given)
 *   c) extract-import-map.mjs <out>/im-input.json <out>/im-output.json
 *   d) build <out>/es-input.json (batchFiles + batchImportData from step c)
 *   e) extract-structure.mjs <out>/es-input.json <out>/es-output.json
 *
 * No new dependencies: Node builtins only. The sibling scripts are
 * spawned as child processes with NODE_PATH pointing at this package's
 * node_modules — the vendored .mjs scripts resolve
 * @understand-anything/core via a pluginRoot two directories up (the
 * upstream plugin's layout), which does not exist here; NODE_PATH
 * supplies the resolution without touching the vendored scripts.
 *
 * Output: summary on stdout; child logs pass through on stderr.
 * Any step failing => exit != 0 with a clear message.
 */

import { spawnSync } from 'node:child_process';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';

const __dirname = dirname(fileURLToPath(import.meta.url));

function fail(message) {
  process.stderr.write(`extract.mjs failed: ${message}\n`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------
const args = process.argv.slice(2);
let repoRoot;
let outDir;
let excludeValue;
let lang;

for (let i = 0; i < args.length; i++) {
  const arg = args[i];
  if (arg === '--out' || arg === '--exclude' || arg === '--lang') {
    const value = args[i + 1];
    if (value === undefined || value.startsWith('--')) {
      fail(`${arg} requires a value`);
    }
    if (arg === '--out') outDir = value;
    else if (arg === '--exclude') excludeValue = value;
    else lang = value;
    i++;
    continue;
  }
  if (arg.startsWith('--')) {
    fail(`unknown option: ${arg}`);
  }
  if (!repoRoot) {
    repoRoot = arg;
    continue;
  }
  fail(`unexpected argument: ${arg}`);
}

if (!repoRoot || !outDir) {
  process.stderr.write(
    'Usage: node extract.mjs <repoRoot> --out <dir> ' +
    '[--exclude "pattern1,pattern2"] [--lang <language>]\n',
  );
  process.exit(1);
}

if (!existsSync(repoRoot) || !statSync(repoRoot).isDirectory()) {
  fail(`repoRoot is not an existing directory: ${repoRoot}`);
}

mkdirSync(outDir, { recursive: true });

const scanOutputPath = join(outDir, 'scan-output.json');
const imInputPath = join(outDir, 'im-input.json');
const imOutputPath = join(outDir, 'im-output.json');
const esInputPath = join(outDir, 'es-input.json');
const esOutputPath = join(outDir, 'es-output.json');

// ---------------------------------------------------------------------------
// Child spawning
// ---------------------------------------------------------------------------
const childEnv = {
  ...process.env,
  NODE_PATH: join(__dirname, 'node_modules'),
};

function runStep(label, scriptName, scriptArgs) {
  const scriptPath = join(__dirname, scriptName);
  if (!existsSync(scriptPath)) {
    fail(`${label}: script not found: ${scriptPath}`);
  }
  const result = spawnSync(process.execPath, [scriptPath, ...scriptArgs], {
    env: childEnv,
    stdio: ['ignore', 'inherit', 'inherit'],
  });
  if (result.error) {
    fail(`${label}: could not spawn node — ${result.error.message}`);
  }
  if (result.status !== 0) {
    fail(`${label}: ${scriptName} exited with code ${result.status}`);
  }
}

function readJson(label, path) {
  let raw;
  try {
    raw = readFileSync(path, 'utf-8');
  } catch (err) {
    fail(`${label}: could not read ${path} — ${err.message}`);
  }
  try {
    return JSON.parse(raw);
  } catch (err) {
    fail(`${label}: invalid JSON in ${path} — ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// a) scan
// ---------------------------------------------------------------------------
const scanArgs = [repoRoot, scanOutputPath];
if (excludeValue !== undefined) {
  scanArgs.push('--exclude', excludeValue);
}
runStep('step a (scan)', 'scan-project.mjs', scanArgs);

const scan = readJson('step a (scan)', scanOutputPath);
if (scan.scriptCompleted !== true || !Array.isArray(scan.files)) {
  fail(`step a (scan): unexpected output shape in ${scanOutputPath}`);
}

// ---------------------------------------------------------------------------
// b) im-input
// ---------------------------------------------------------------------------
const selectedFiles = lang
  ? scan.files.filter(file => file.language === lang)
  : scan.files;

if (selectedFiles.length === 0) {
  fail(
    lang
      ? `step b (im-input): no files with language "${lang}" in scan output`
      : 'step b (im-input): scan produced zero files',
  );
}

const imInput = {
  projectRoot: repoRoot,
  files: selectedFiles.map(({ path, language, fileCategory }) => ({
    path,
    language,
    fileCategory,
  })),
};
writeFileSync(imInputPath, JSON.stringify(imInput, null, 2) + '\n', 'utf-8');

// ---------------------------------------------------------------------------
// c) import map
// ---------------------------------------------------------------------------
runStep('step c (import-map)', 'extract-import-map.mjs', [imInputPath, imOutputPath]);

const imOutput = readJson('step c (import-map)', imOutputPath);
if (imOutput.scriptCompleted !== true || typeof imOutput.importMap !== 'object' || imOutput.importMap === null) {
  fail(`step c (import-map): unexpected output shape in ${imOutputPath}`);
}

// ---------------------------------------------------------------------------
// d) es-input
// ---------------------------------------------------------------------------
const esInput = {
  projectRoot: repoRoot,
  batchFiles: selectedFiles.map(({ path, language, sizeLines, fileCategory }) => ({
    path,
    language,
    sizeLines,
    fileCategory,
  })),
  batchImportData: imOutput.importMap,
};
writeFileSync(esInputPath, JSON.stringify(esInput, null, 2) + '\n', 'utf-8');

// ---------------------------------------------------------------------------
// e) structure
// ---------------------------------------------------------------------------
runStep('step e (structure)', 'extract-structure.mjs', [esInputPath, esOutputPath]);

const esOutput = readJson('step e (structure)', esOutputPath);
if (esOutput.scriptCompleted !== true) {
  fail(`step e (structure): unexpected output shape in ${esOutputPath}`);
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
const totalEdges =
  imOutput.stats && typeof imOutput.stats.totalEdges === 'number'
    ? imOutput.stats.totalEdges
    : Object.values(imOutput.importMap).reduce((sum, targets) => sum + targets.length, 0);
const skipped = Array.isArray(esOutput.filesSkipped) ? esOutput.filesSkipped.length : 0;

process.stdout.write(
  [
    'extract.mjs: done',
    `  repoRoot:        ${repoRoot}`,
    `  files scanned:   ${scan.totalFiles}`,
    `  files selected:  ${selectedFiles.length}${lang ? ` (language=${lang})` : ''}`,
    `  import edges:    ${totalEdges}`,
    `  files analyzed:  ${esOutput.filesAnalyzed}`,
    `  files skipped:   ${skipped}`,
    `  outputs:         ${scanOutputPath}, ${imOutputPath}, ${esOutputPath}`,
  ].join('\n') + '\n',
);
