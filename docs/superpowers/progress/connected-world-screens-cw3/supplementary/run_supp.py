"""Supplementary completion of CW3's failed held run F_CP on procedural 851: the same
command, environment, extractor and identity checks, on a git archive of the frozen held
source b9170bef, with the shared native extension; into a separate output directory."""
import json, sys
from pathlib import Path
TREE = Path("/home/user/evidence/cw3/supp/tree").resolve()
OUT = Path("/home/user/evidence/cw3/supp/out").resolve()
HELD = Path("/home/user/evidence/cw3/held")
sys.path.insert(0, str(TREE / "scripts"))
import screen_runner as SR, connected_world_screens as CW  # noqa: E402  (the archive's own)
assert SR.REPO == TREE, SR.REPO
screen = CW.SCREENS["CW3"]
import subprocess
p = subprocess.run([SR.PY, "-c", SR._WHICH], cwd=SR.REPO, env=SR._run_env(), capture_output=True, text=True)
which = p.stdout.split("\n")
assert which[0].startswith(f"{TREE}/src/"), which
lines = SR.identity_lines("b9170bef9729c81a0063a9395c6e9085c61ed0fe", 0, which[0], which[1], screen, dirty_code=0)
lines.append(SR.preregistration_line(screen))
held_lines = [l for l in (HELD / "source.txt").read_text().splitlines()][:len(lines)]
compare = [(a == b, a, b) for a, b in zip(lines, held_lines)]
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "source.txt").write_text("\n".join(lines) + "\nsupplementary: F_CP p851 only (the held run's failed run, "
                                "an infrastructure failure); not part of the frozen result\n")
held_digest = json.loads((HELD / "held-run.json").read_text())["identity"]
row = SR.run_one(screen, SR.Runtime(identity=lambda s: lines), OUT, "held", "F_CP", "p", 851, keep=True,
                 identity=SR.identity_digest(lines))
row["supplementary"] = True
(OUT / "metrics.jsonl").write_text(json.dumps(row) + "\n")
print(json.dumps({"rc": row["rc"], "wall_s": row.get("wall_s"), "activation": row.get("activation"),
                  "identity_supp": row["identity"], "identity_held": held_digest,
                  "error": row.get("error", "")[-300:]}, indent=1))
for same, a, b in compare:
    print("same" if same else "DIFFERS", "|", a, "|", b if not same else "")
