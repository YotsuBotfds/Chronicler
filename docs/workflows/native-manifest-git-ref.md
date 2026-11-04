# Check the native shard layout before pushing

The optional immutable-ref check catches an unassigned new test module before a
hosted native build. The first retained-Kin care CI failed closed because its
manifest owned 300 modules while its commit contained 302. The bounded offline
selection's `--list` describes a different selection and cannot establish this
full native module registration.

Use the updated control script with an available **full lowercase 40-hex commit**
in the local Git store. The target commit need not be physically checked out:

```sh
GIT_DIR=/absolute/path/to/repository.git python /absolute/path/to/control/scripts/native_ci_shards.py check-manifest --execute --source-ref FULL_40_HEX_COMMIT --output /tmp/native-layout-frozen-commit.json
```

For an ordinary checkout, omit `GIT_DIR`; the script uses its repository root.
No fetch, source import, pytest collection, World, native load or build occurs.
The output must be a new file. A missing commit, non-commit object, mutable/short
ref, absent or nonregular manifest/test entry, new/missing module or duplicate
owner refuses admission. Git replacement objects and automatic lazy fetching
are disabled per read in this mode; absent local objects refuse without fetching.

The script reads the manifest blob and the tracked default `test_*.py` / `*_test.py`
paths under `tests/` from the **same commit tree**. It delegates exact ownership
to the existing two-shard validator. It does not assign modules, change skip or
subtest seals, or relax any producer/consumer gate. Its PASS records the requested
commit, tree, manifest blob, original-byte SHA-256, canonical manifest digest and
module count; the scope is Git layout only. It is not actual pytest collection,
test success, native/schema identity, scientific qualification or a CI grant.

`--source-ref` is valid only for `check-manifest`. The existing explicit
`--execute` requirement remains. Omitting `--source-ref` retains the physical
manifest/current-index check and its original output bytes. `record-build`,
`verify-transfer`, `run`, `aggregate` and every workflow remain unchanged.

Qualification for this source is a small guarded metadata-only run of the
existing controller test module with finite Git doubles, not a full/native CI
run. Source publication and any hosted qualification remain separately reviewed.
