# Chronicler Viewer

Open a local legacy `chronicle_bundle.json` with **Open Existing** (any bundle
version; version 6 is decoded on load by `src/lib/bundleCodec.ts`). Expand
**Inspect region history** to filter exported region observations and events by
turn, region, and metric, with original-file identity and missing-data labels.
See [the inspector guide](../docs/experiment-inspector.md) for evidence semantics,
the deterministic fixture, and local browser QA. The panel is closed by default
and limited to static artifacts.

Bundles that record the simulation systems (epidemics, food, wars, finance,
diplomacy, techniques, maritime, nomads, agendas, governance, contact) also
get a **Simulation systems** panel below the map with one tab per recorded
system, a **Map layer** row (food, epidemics, wars, migration, techniques,
sea) and per-region food, war, epidemic and technique rows in the inspector;
bundles without them get none of these. See
[viewer-systems.md](../docs/integration/viewer-systems.md).

## Live checkpoint browser QA (opt-in, not CI)

`scripts/qa-live-checkpoint.mjs` drives the live pause panel's **Save
checkpoint** and `--live --resume` in headless Chromium (Playwright,
`require("playwright")`). Start the viewer (`npm run dev`, or `npm run build`
and `npm run preview`), then from `viewer/`:

```sh
PYTHONPATH=../src node scripts/qa-live-checkpoint.mjs --python <python with chronicler's dependencies> \
    [--viewer http://localhost:5173] [--agents off] [--out DIR]
```

It starts its own `--live --simulate-only` sessions (stopped by their PIDs),
launches a 20-turn world from the setup form, saves a checkpoint at the pause
at turn 5, resumes it with `--live --resume`, checks the resumed viewer's
history and pause, and checks that a stale or missing session token is
refused. Screenshots, logs and `report.json` go to `--out`. See
[checkpoint-continuation.md](../docs/integration/checkpoint-continuation.md),
section 11.

## React + TypeScript + Vite scaffold notes

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
