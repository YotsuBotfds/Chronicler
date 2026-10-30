# Manual C-only kernel capability preflight — source only

This separate701-based branch asks whether a hosted Linux environment can
install Landlock ABI >=3 and an x86_64 seccomp filter and enforce the sampled
fixture permissions. The workflow is **manual only**, branch restricted and
UNRUN. Publication and the first hosted dispatch require separate root review.
There is no Python setup, package installation, native extension, wheel,
simulation, World, campaign, profiler or application network operation. The
trusted pre-jail socket baseline only creates/closes an unconnected socket.
Checkout and evidence upload are platform workflow operations.

The local predecessor compiled successfully, producing a23,096-byte ELF with
SHA256`5a08d051f809a99c3d4502107e8bd70556ed49caf37c71438d90fc6b75eed5d0`.
Its separately approved first fixture attempt exited2: baseline mask1, stage3,
Landlock ABI-query errno38/ENOSYS. No Landlock rule or seccomp installation was
exercised. All three fixture bodies stayed exact, files0444 and directory0555.
The root negative SHA256 is
`896d94eb86bd6dacd79ebef0a319be2376e9dbc9ce359c941ba55f31a31af2e6`;
independent saved reconciliation is
`a24917440893f11fbcd40acb3116878522cdfee63643cded56addda6c4a7c1ce`.
Those are local-context results, not proof of the kernel build configuration or
an external interception cause. Compiler aggregate CPU and combined external
compile/probe CPU/wall were not measured. The C report measures only its own
probe parent/worker. No local retry is proposed.

The hosted C successor changes only the temporary fixture prefix and stricter
worker CPU20s, parent wait100s and per-file760KiB output bounds. The Landlock,
BPF, architecture/x32, descriptor and14-check logic stays exact. The worker
still closes all inherited file descriptors except its one write-only status
pipe, grants READ_FILE only to the exact allowed inode, handles filesystem
rights through TRUNCATE, and denies writes/socket/process/unknown calls. Safe
invalid-clone3 and empty-path-execve samples cannot launch anything if the
filter fails. Exactly one fresh three-file fixture is created only after the
compiler and code-cap gates succeed.

The complete trusted Bash command tree is measured with GNU time: setup,
compiler, C owner/worker and fixture/evidence closure. Raw aggregate user/system,
elapsed wall, exit and maximum-child RSS are retained. GNU time's own process,
outer wrapper checks/sealing, checkout and upload are outside that command-tree
measurement and are explicitly labelled; they are not silently presented as
measured external whole-lifecycle cost. Maximum-child RSS is not aggregate RAM.

The tree runs on one CPU under512MiB per-process AS and30CPU hard ceilings.
The Bash owner has a1CPU soft cap; compiler wall is at most3s; the two metadata
phases together have at most1s wall on that CPU; C parent4CPU + worker20CPU
leaves a1CPU accounting margin below30. Actual command-tree CPU must additionally
be <=29s. An outer108s timeout with1s kill escalation and the C100s wait deadline
keep the measured tree below the existing110s wall ceiling; actual elapsed must
be <=109s. Unknown metrics, resource excess or missing closure is negative.

Before fixture execution, the actual retained source copies, workflow/generated
owner allowance and compiled ELF must fit the existing512KiB code reserve.
Compiler stderr and ELF each have a stricter128KiB file-size cap; the C capture
has760KiB. The conservative final payload reservation remains
`2*760KiB logs +512KiB code +16KiB metadata =2MiB`. Retained source/binary,
compiler/kernel/source identities, raw logs, measurement, three tiny fixture
copies and hash manifest are all charged. An over-limit/unknown output namespace
prevents evidence upload instead of raising the limit. Partial failure is not
retried or called successful. The original fixture remains untouched after
its C readonly closure; retained copies are evidence, not a second experiment.

Compiler, dynamic loader/libc and GitHub runner/actions remain platform TCB.
Their observed identities are not immutable external read leases. A hosted
positive would establish only this C fixture's sampled enforcement in that
particular environment. It would not establish CPython/native compatibility,
external runtime permission leases, the final installed bootstrap/owner,
32MiB whole-owner fit, an installed API, trajectory/RNG/scientific/performance
qualification, or promotion to main. No source author has compiled or run this
hosted successor or dispatched this workflow.
