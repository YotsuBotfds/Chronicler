# Actual complete-window residence and public-health browser follow-up

The saved corrected AD-p19 pilot now supplies the complete-window witness that was unavailable in the 8-turn smoke. The viewer remains frozen at `71accf9449965ac77936e69f0391ef9a43b5bbcd`; this follow-up changes only documentation and evidence tools. No simulation, performance profile, new held seeds or default promotion was run by the viewer lane. Earlier real v6 legacy and gzip compatibility evidence is retained unchanged.

Input: `/workspace/evidence/cwr-evaluation/pilot-8792be88-v1/runs/AD-p19/chronicle_bundle.json`, SHA-256 `b9d42be3b1d2417165ec9e889d1d7543cefca63fd2dc7037eb7b7831cce5a8c6`. This is the existing procedural seed19 development pilot, 32 regions and 120 recorded snapshots, not fresh held qualification. The [producer receipt](complete120-producer.txt) records clean source `8792be88dd36ba4d7c22e480de6a19dd64ea1300`, native SHA `b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd`, runner, screen and registry identities. The broader causal evaluation remains the lead lane's evidence.

All 120 snapshots pass the production corrected readers. All **197,271** indexed observations have resolving pointers and clocks strictly before their saved snapshot, including the configured current-turn neutral multiplier. These are the corrected bundle's observations, not an identity comparison with the old FULL-p19 bundle. [Full reader receipt](complete120-readers.json).

The first actual complete positive-arrival X1 window occurs at snapshot22. The public-health observation reads that completed X1 frame one snapshot later. Selected browser snapshots were chosen from the actual saved diagnostics, not edited to create a complete result:

| Snapshot | X1 source turn | Current X1 arrivals / unknown latest reason | X1 window | PH residence source | PH arrival window | Configured multiplier source |
|---:|---:|---:|---|---:|---|---:|
| 1 | 0 | 0 / 0 | Incomplete | −1 | Unrecorded | 0 |
| 22 | 21 | 226 / 226 | Complete | 20 | Incomplete | 21 |
| 23 | 22 | 242 / 242 | Complete | 21 | Complete | 22 |
| 120 | 119 | 464 / 459 | Complete | 118 | Complete | 119 |

There are 99 saved complete positive-arrival X1 windows and 98 later public-health snapshots with complete, positive regional arrival shares. The new counts are physical residence-arrival diagnostics, not forced-displacement counts or measured housing pressure. Unknown motive remains unknown. The configured extra susceptibility multiplier stays exactly one in corrected explicit `density_only` mode, including regions with large arrival shares and zero motive-classified spell share. Existing epidemic density remains the health authority.

Independent readback checks **all 3,840 regional public-health observations** against the X1 record dated one turn earlier. Every complete share equals that prior region's recent arrivals divided by observed residents (with the specified empty-region zero); every incomplete/unrecorded share remains null. Current configured multiplier dates are checked separately. **2,392** observations differ from what a same-turn lookup would yield, providing an actual source-clock witness. This arithmetic comparison is not a simulated alternate story. [Readback](complete120-arrival-clocks.json), [all candidates](complete120-window-candidates.json), [reproduction tool](verify-arrival-clocks.py).

The actual production Chromium journeys pass **372/372 assertions**, 186 each on desktop and phone touch viewports. They check snapshots1,22,23,120; exact retained combined/A6/D3/would score tables; positive X1 counts and completeness wording; all 32 regional public-health rows at each selected snapshot; incomplete versus complete shares; current multiplier versus prior residence dates; exact linked individual pointers; pagination; and prose/table containment. No page or console errors occurred. [Browser receipt](complete120-browser.json), [inspected phone health screenshot](complete120-phone-health-T23.png), [inspected phone residence screenshot](complete120-phone-residence-T23.png).

The first expanded journey had six failed harness assertions out of 366: it assumed an installed migration-input row appeared among the first 24 linked-history rows. The other 360 checks passed, including every PH row and source clock. One ordinary **Show earlier observations** click exposes the exact current-snapshot pointer at snapshots22,23,120 on both viewports. The corrected harness follows that existing pagination and checks the specific row, rather than accepting an unrelated older row. No UI/source fix was needed. The [initial receipt](complete120-initial-pagination-assumption.json) is retained; no measured timing samples or model outcomes were discarded.

Reproduction uses the existing saved bundle and the reviewed build:

```sh
node docs/superpowers/progress/connected-world-rework-viewer-compatibility/validate-corrected.mjs "$PWD" /path/AD-p19/chronicle_bundle.json /tmp/complete120-readers.json
PYTHONPATH=src python docs/superpowers/progress/connected-world-rework-viewer-compatibility/verify-arrival-clocks.py /path/AD-p19/chronicle_bundle.json /tmp/complete120-clocks.json
NODE_PATH=/path/to/playwright/node_modules CHROMIUM_EXECUTABLE=/usr/bin/chromium PYTHONPATH=src node docs/superpowers/progress/connected-world-rework-viewer-compatibility/journey-corrected.mjs "$PWD/viewer/dist" /path/AD-p19/chronicle_bundle.json /tmp/complete120-browser /path/to/python 1,22,23,120
```

The original full viewer suite, focused follow-up checks, legacy/gzip journeys, adverse loading measurements and large-chunk warnings remain as recorded in the [main packet](README.md). This docs-only follow-up does not rerun simulation/native tests or the restricted qualification gates. It resolves the missing real complete-window browser witness; it does not establish causal benefit, performance improvement, every-browser support or physical handset behavior.
