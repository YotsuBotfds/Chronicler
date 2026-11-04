# Local simulate, view, and exact-resume walkthrough

This Mac/Linux example uses a small real world, no narration service, and an
exact checkpoint. It leaves every optional simulation switch at its default.
Use an environment without `chronicler_agents` for the aggregate/no-native lane;
`--agents off` alone does not disable native ecology or politics when that
extension is installed.

## 1. Set up

From the repository root:

```sh
uv sync --frozen --python 3.13
.venv/bin/python scripts/check_python_env.py --expect no-native
```

Without uv, `python3.13 -m venv .venv` and `.venv/bin/python -m pip install -e .`
install unlocked versions instead; the check applies either way.

No API key, LM Studio server, or paid narration is used below.

## 2. Simulate and save an exact checkpoint

```sh
export PYTHONHASHSEED=0
.venv/bin/python -m chronicler.main \
  --seed 42 --turns 8 --civs 2 --regions 5 \
  --agents off --simulate-only \
  --output output/kimi-e7/reference/chronicle.md \
  --state output/kimi-e7/reference/state.json \
  --checkpoint-every 4 \
  --checkpoint 'output/kimi-e7/reference/ckpt/turn_{turn:04d}.ckpt'
```

This writes the chronicle, world state and sidecars, memory files, viewer
bundle, and exact checkpoints after turns 4 and 8.

## 3. Resume from turn 4

Keep the same `PYTHONHASHSEED`, then resume the turn-4 checkpoint rather than
the finished run:

```sh
.venv/bin/python -m chronicler.main \
  --resume output/kimi-e7/reference/ckpt/turn_0004.ckpt \
  --turns 8 \
  --output output/kimi-e7/resumed/chronicle.md \
  --state output/kimi-e7/resumed/state.json
```

The checkpoint supplies the seed, mode, and simulation switches. Resuming a
pre-final checkpoint continues the uninterrupted trajectory; extending a
finished run has different final-turn settlement semantics.

To check this sample's outputs:

```sh
.venv/bin/python - <<'PY'
from pathlib import Path
from chronicler.bundle_codec import load_bundle

root = Path("output/kimi-e7")
reference = root / "reference"
resumed = root / "resumed"
names = ["chronicle.md", "state.json", "state.historiography.json", "state.languages.json"]
names += [path.name for path in reference.glob("memories_*.json")]
for name in names:
    assert (reference / name).read_bytes() == (resumed / name).read_bytes(), name

before = load_bundle(reference / "chronicle_bundle.json")
after = load_bundle(resumed / "chronicle_bundle.json")
for bundle in (before, after):
    bundle["metadata"].pop("generated_at")
assert before == after
print(f"Matched {len(names)} artifacts byte-for-byte; bundles match except generated_at.")
PY
```

A legacy resume from `state.json` is not this exact-checkpoint contract.

## 4. Open the real bundle in the viewer

In a second terminal, from the repository root:

```sh
cd viewer
npm ci
npm run dev
```

Open the printed local URL (normally <http://localhost:5173>), choose **Open
Existing**, and select `output/kimi-e7/reference/chronicle_bundle.json` from the
repository. The archive opens at turn 1 of 8; use the timeline to inspect later
turns and **Inspect region history** for region observations. Static bundle
viewing does not start a simulation or a live-session WebSocket.

## Verified example and limits

On 2026-11-01, source `01ab4104b4e83bd50047abe0ad8f347af7453d33`
produced an eight-turn Aetheris sample with seed 42. Six chronicle/state/
sidecar/memory artifacts matched byte-for-byte after the turn-4 resume; every
decoded bundle field matched except the expected `metadata.generated_at`
timestamp. On Node 20.20.2, headless Chromium used **Open Existing** to render
that actual bundle as Aetheris, seed 42, turn 1 of 8, with all five regions and
no viewer or page errors.

The Python evidence used CPython 3.12.12 with persisted dependencies and
`chronicler_agents` absent; it is aggregate/no-native execution evidence, not a
fresh Python 3.13 installation or native qualification. The viewer install used
the lockfile on ordinary scratch storage because the repository portal mount
cannot create npm's symlinks. No fresh CI, full determinism profile, or
scientific gate is claimed. Generated runs and browser evidence remain ignored
local artifacts, not committed fixtures.
