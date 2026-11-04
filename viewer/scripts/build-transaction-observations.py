"""Copy actual transaction summaries, with source labels/hashes; invent no world rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from chronicler.bundle_codec import load_bundle

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path, help="Folder of controlled fixture subdirectories")
parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "src/__fixtures__/transaction_observations.json")
args = parser.parse_args()
fixtures = {}
for source in sorted(args.source.glob("*/chronicle_bundle.json")):
    bundle = load_bundle(source)
    label = bundle["metadata"].get("fixture_source")
    if not label:
        raise ValueError(f"Missing fixture-source label in {source.name}")
    history = [{"turn": row["turn"], "transaction_receipts": row["transaction_receipts"]}
               for row in bundle["history"] if "transaction_receipts" in row]
    fixtures[source.parent.name] = {"source": {**label, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}, "history": history}
if not fixtures:
    raise ValueError("No actual controlled transaction fixtures found")
args.output.write_text(json.dumps(fixtures, separators=(",", ":")) + "\n")
