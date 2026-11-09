/**
 * Load Playwright for the opt-in viewer QA and performance scripts.
 *
 * Playwright is an optional peer dependency (see viewer/package.json and
 * viewer/README.md): `npm ci` does not install it. Cloud containers have it
 * globally; elsewhere install it outside the lockfile.
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

export function loadPlaywright() {
  try {
    return require("playwright");
  } catch (error) {
    throw new Error(
      "Playwright is not installed; install it globally (cloud sessions have it) "
        + "or `npm i --no-save playwright`.",
      { cause: error },
    );
  }
}
