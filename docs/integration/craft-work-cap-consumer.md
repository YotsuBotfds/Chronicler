# Optional city crafts capacity consumer

Implemented on `lead/public-production-audit`: preregistration/source audit
`9861e68e`, code and regressions `6fc52f9b`. This adds a consumer to the existing
city-economy column builder, not an active workshop or mill. Existing simulation
callers omit the new argument.

```python
region_input = with_economy_columns(
    world, region_input, snapshot, craft_work_caps={2: 0.5},
)
```

Both `cities.economy_columns` and `cities.with_economy_columns` accept the
keyword-only optional mapping. Region indices are positions in `world.regions`;
the units are raw loads per current call. Specified regions use at most their
legacy craft raw-demand ceiling and the supplied cap; unlisted regions retain
legacy capacity. Zero is a binding zero. A cap is shared by all cities in the
region. It cannot raise production or create capacity where no city exists.

Caps validate as integer region indices and finite nonnegative real values,
excluding booleans. Validation happens when city columns can be built; cities
off or missing/invalid agent rows keep the existing absent-column behavior.
Malformed mappings or bounds raise rather than quietly fall back. When nearest
Float32 rounding would exceed a cap, the exported bound is lowered to the next
representable value. `None` and an empty mapping preserve legacy column bytes.

The ceiling remains the existing `craft_raw_demand` field, so this also reduces
raw-market demand. Existing native conversion still consumes available raw
inputs one for one into wares, after excluding committed merchant departures.
The consumer leaves farming allocation, wares demand, stock settlement, income
formulas and RNG unchanged. Active caps can change downstream market prices,
income values, trade and welfare. No promise of active-economy identity is made.

The caller must supply a defensible capacity. This function does not reserve
labor, verify employee availability, measure useful work, collect an upkeep
payment or establish public ownership. There is no runtime planner, CLI flag,
saved state, new receipt, event, native ABI change or checkpoint migration.
Caps are call-local and never persist into another turn or a restored world.
Active overhead is O(number of supplied region caps), reusing the existing
city snapshot aggregation with no further agent scan.

The [source audit](public-workshop-source-audit.md) records the closed raw/work/
cash equations and the blockers before a public operation can activate. In
particular, authoritative adult city-farmer availability must draw only from
already-diverted city time; it must not subtract farming twice. Public treasury
sinks are not worker wallets. River paths and dimensionless water are not
measured discharge/head or free power. Those blockers remain open.

## Focused verification, 2026-10-28

Linux, Python 3.13, one-thread caps, shared qualification load concurrently.
These elapsed times describe focused tests, not simulation performance.

| Check | Result |
| --- | --- |
| `pytest -q tests/test_city_markets.py -k craft_work_cap` | 23 passed, 9 deselected, 0.78 s |
| `pytest -q tests/test_city_markets.py tests/test_crafts.py -m 'not native'` | 32 passed, 7 deselected, 0.58 s |
| Same two files under `python_oracle_guard` | 32 passed, 7 native skips, 1.01 s; guard PASS, no native modules loaded or blocked I/O |

Default checks compare known legacy city values and Arrow bytes and verify
unchanged world JSON, snapshot bytes and Python RNG state. Bounds include
multiple cities, absent cities/rows, zero, nonfinite/invalid types, a cap between
the Python ceiling and its Float32 rounding, and subnormal underflow. Repeated
calls and JSON/pickle world restores do not retain caps.

The native mechanical check uses the existing receipt release extension:
SHA-256 `fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317`,
matching the unchanged crate tree
`a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`. No Rust rebuild was performed.
It verifies zero/partial/full actual wares output, scarce/absent raw inputs,
unchanged food work across caps, restored capacity on omission, and unchanged
native checkpoint bytes while constructing inputs. Synthetic city rows set
capacity in that fixture; they are not evidence of available workers.

The existing bounded oracle `systems-1` chunk already selects the changed
`test_city_markets.py`; no chunk or 110-second limit changed. Independent
read-only review found no blocker in this consumer and agreed that activation
remains blocked. No new simulation study, full gate or performance measurement
was run. External evidence and source/binary hashes are retained at
`/workspace/chronicler-public-production-evidence/manifest.json`; that private
workspace path is an evidence locator, not a portable build prerequisite.
