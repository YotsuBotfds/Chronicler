# Prospective remote runtime policy for natural research continuation

Status: design only. No new native binary is admitted by this document, no
workflow is active, and no natural-study world has run. The inactive adapter
still requires its originally identified `fb20dbc8` binary. The fixed eight
seeds, arms, scientific clocks, thresholds and resource caps are unchanged.

The current machine cannot meet the study's 6 GiB disk admission floor. A remote
execution could reuse an officially retained, freshly built wheel instead of
performing another native build. The proposed compiled binary is
`06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6`,
from unchanged Rust crate tree `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`.
That binary was used in the completed recovered-default-output study
`40796958774`, whose candidate was `c76efe85`. This does not make it identical to
the earlier `fb20dbc8` composition-proof binary or qualify the new study.

Before changing the adapter's allowed binary, create a separate prospective
execution registration naming the independently reviewed harness commit,
unchanged scientific registration hash, exact producer commit `c76efe85`, and
the selected wheel's official producing run, artifact ID, ZIP digest, wheel
digest and manifest. Verify the artifact and wheel bytes against that manifest;
do not infer the wheel digest solely from its compiled module digest. Retain
the original binary policy and every earlier failed proof.

The separate execution registration must require:

- Exact unchanged producer and Rust crate identities, and byte-identical clean
  producer/control roots before freezing their observed paths and Git refs.
- Verified compiled module origin and digest, all three real compiled exports
  and schema fingerprints, plus the actual active native sections at restore.
  Available classes do not establish three active pools.
- Exact observed Python patch, packages, hash seed, one affinity CPU and thread
  caps shared across every parent, fork and reader. A saved environment label
  is insufficient.
- A new full prospective source/runtime/control freeze before the first world,
  with no runtime substitution, source mutation, scientific-outcome probe or
  favorable seed replacement after freezing.
- Qualification of this exact adapter's restoration, pruning, ownership,
  accounting and publication contracts. Prior default-output parity does not
  establish checkpoint or global-RNG continuation identity.
- The original disk/RAM admission and running floors, 900 CPU-second cap
  including conservative finalization accounting, and complete evidence
  retention. Remote capacity does not expand those budgets.

The eventual source change should use a small closed registration of explicitly
qualified binary policies rather than accepting any supplied digest. This
document is an assessment of that option. It contains no artifact download,
activation command or permission to silently replace the existing binary.
