# Optional lossless bundle archives

This is a storage/transport option for an **existing saved JSON file**. It does
not rerun the model, change the normal JSON writer, omit events, alter identity,
reduce the declared world or claim a simulation, loading or memory speedup.
The original file is retained. Keeping both copies increases total local disk
usage; the smaller figures below describe the gzip representation alone.

Implementation source: `4634a69da177c4bfa0caf62ad380a9fe39d43639`, based on
main `2726bf449d0e4d581a72034000ee0861a58ee439`. The [source receipt](source.json)
identifies exact codec, script and test hashes. No dependency or native build
is added. The unchanged default writer still emits ordinary version-6 JSON.

`archive_bundle` checks JSON-object syntax, hashes the original bytes, writes a
gzip stream with fixed time and no embedded filename, then decompresses it and
compares the complete bytes against the unchanged source before publication.
Same-directory hard-link publication refuses a destination created concurrently
instead of overwriting it. Source changes, compression errors and truncated or
corrupt archives are explicit failures. Temporary files are removed. Existing
outputs and originals are never replaced or deleted.

This is transport verification, not a claim that a malformed history patch or
scientific model became valid. `load_bundle` recognizes gzip by magic bytes and
then runs the existing JSON and version-6 decoder. Versions 1–6, number types,
key order, Unicode, signed zero and missing/null versus zero keep their old
semantics. Model/reader validation remains authoritative. The archive has its
own byte identity; the receipt records both source and archive SHA256 values.

## Measured representation cost

The same fixed historical FULL saved files were used, without another model
run. The stress case started at 43,700 agents and peaked at 53,138; its name does
not establish a 52,000-agent initial population. The 120-turn natural bundle is
exact source SHA256 `f6cb5562a4aaec888b6f2a03b4c4b01bd1e8d49737aec22673034eba30ce0ee2`.
The 200-turn file is the transparently profiled main `2726bf44` dataset; the 150/20-turn
files are the retained eaa4a5d3 profile datasets. Full raw file hashes are in
the receipts; metadata timestamps are not normalized for these byte checks.

| Saved dataset | JSON MiB | gzip level 1 MiB | Representation smaller | Archive total CPU s | Archive peak RSS MiB | Plain/gzip load CPU s | Plain/gzip load peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| procedural32 seed19,120T |36.20|9.02|75.08%|1.237|296.9|4.000/3.849|628.0/628.6|
| procedural32 seed19,200T |68.13|16.63|75.59%|2.240|544.3|7.236/7.495|1190.1/1190.7|
| procedural48 seed42,150T |53.03|12.98|75.53%|1.735|430.2|5.436/5.568|927.6/928.0|
| historical stress seed7,20T |7.58|1.17|84.51%|0.203|81.3|0.406/0.413|107.9/108.5|

Archive total CPU includes syntax validation, compression, complete byte
verification and publication. The compression step alone costs 0.268 CPU s in
the 120T pilot, but that is not the total operation cost. Every source hash
remained unchanged; all decompressed bytes matched, and every full decoded
tree had the same canonical fingerprint preserving JSON types, order and the
sign of zero. No native module was imported by any measurement process.

There is **no loading or RSS improvement claim**: gzip loading is slightly
slower in three cases, and decoded-memory peaks are effectively unchanged.
The same authoritative expanded history still has to exist. These are single
bounded observations on the shared host, not throughput qualification.

The 120T [timing pilot](pilot120.json) took 11.30 seconds wall for archive and
both fresh-process loads, including verification fingerprints. Scaling its
time by the remaining input sizes projected about 41 seconds; a fixed 90-second
elapsed cap was chosen before those three cases. They completed in 38.65 seconds,
with no failure or limit increase: [remaining-case receipt](representative.json).
Each operation used a separate fresh Python 3.13.16 process and ran serially;
load timing excludes the separately reported verification-fingerprint time.
Peak RSS fields are process high-water marks, not sampled increments.

## Encoder investigation and null result

The main `2726bf44` procedural19/200T cProfile attributes 41.75 instrumented seconds to
`encode_history`. Nested cumulative values overlap: `same` 11.8 million calls/
15.97s; `_literal` 3.27 million/5.48s including `_check_keys`; JSON `_dumps`
576,821 calls/8.17s. Instrumented values are not uninstrumented runtime costs.

A proposed shortcut returned changed scalar replacements directly before
container dispatch, avoiding a reserved-key traversal that does nothing for a
scalar. Three alternating exact-data trials retained the same 71,441,011-byte
encoded SHA256 on every trial. Old CPU was 8.922/9.091/8.898 seconds; candidate
8.984/8.884/8.815 seconds. The median difference is about 0.4%, with overlapping
ranges. **It was not admitted.** The encoder and all patch/size decisions are
unchanged. [Raw probe receipt](encoder-probe.json), [output](encoder-probe.log)
and [frozen-source reproducer](probe_encoder.py) retain the null result.

## Checks and reproduction

The existing enrolled codec test module passes **48 tests**, including six old
layout versions, signed zero/type/order/null round trips, corrupt/truncated
gzip, preserved existing patch errors, deterministic headers, source changes,
concurrent destination creation, disk-write failure and CLI behavior:
[focused test log](focused-tests.log). The wider codec/bundle/analytics suite passed
139 tests with 2 skips: [relevant suite log](relevant-tests.log). Existing standard test fixtures include
a short Python-only run; no new evaluation or held simulation was performed.
Viewer gzip upload/worker behavior is a separate integration/review gate.
Full exact-head CI and feature-off checks belong to the lead's integrated PR.

```sh
PYTHONPATH=src python scripts/cw_bundle_archive.py \
  --source RAW/chronicle_bundle.json --output NEW/chronicle_bundle.json.gz
PYTHONPATH=src python -c 'from chronicler.bundle_codec import load_bundle; import sys; print(len(load_bundle(sys.argv[1])["history"]))' NEW/chronicle_bundle.json.gz

PYTHONPATH=src python docs/superpowers/progress/connected-world-rework-storage/benchmark.py \
  --out NEW_BENCHMARK --case named=RAW/chronicle_bundle.json --budget-seconds 180
python docs/superpowers/progress/connected-world-rework-storage/probe_encoder.py \
  --bundle RAW/chronicle_bundle.json --output NEW_PROBE.json
```

Use new output paths. Archives/raw inputs remain outside Git; only compact
commands, identities, results and tests are retained. No source lifetime after
container reclamation is promised. The published source refs and recorded
commands support reconstruction; no paid narration, held seed, default or
qualification decision changed.
