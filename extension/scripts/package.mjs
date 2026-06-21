#!/usr/bin/env node
/**
 * Package the built extension into a versioned, distributable zip.
 *
 * Run AFTER `npm run build` (the `package` npm script chains both). Produces
 * `release/appfill-<version>.zip` with `manifest.json` at the zip root — the
 * layout Chrome expects when the recipient unzips and "Load unpacked"s, and the
 * layout the Chrome Web Store requires for upload.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { createRequire } from "node:module";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const { version } = require(join(root, "package.json"));

const distDir = join(root, "dist");
const releaseDir = join(root, "release");
const zipName = `appfill-${version}.zip`;
const zipPath = join(releaseDir, zipName);

if (!existsSync(join(distDir, "manifest.json"))) {
  console.error("✗ dist/ not built. Run `npm run build` first.");
  process.exit(1);
}

mkdirSync(releaseDir, { recursive: true });
if (existsSync(zipPath)) rmSync(zipPath);

// Zip from inside dist/ so paths are relative to the extension root.
execFileSync("zip", ["-r", "-q", zipPath, "."], { cwd: distDir, stdio: "inherit" });

console.log(`✓ Packaged release/${zipName}`);
