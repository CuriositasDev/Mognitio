# Version 1.6 verification

Use this guide with the [shared test requirements](README.md#requirements).

## Whole-IR runtime components

The isolated v1.6 runtime probes generate and execute AMD64 ELF files through
Mognitio's own machine records and encoder. They do not change public compiler
commands or establish complete native-profile acceptance.

- `python3 tests/mgnc/v160-x64.py --seed PATH --output NEW_DIRECTORY` checks
  19 independently fixed instruction byte vectors and executes the resulting ELF.
- `python3 tests/mgnc/v160-runtime-plans.py --seed PATH --output NEW_DIRECTORY`
  checks concrete layout and liveness plans, including 17 invalid plans.
- `python3 tests/mgnc/v160-runtime.py --seed PATH --output NEW_DIRECTORY`
  exercises 29 generated runtime cases and five real syscall failure sites.
  Its independent physical-heap oracle checks reachable objects, coalescing,
  exact block-start indexes, free-list membership, and accounting. Cases include
  full-live and fragmented heaps, multiple arenas, stress collection, globals,
  partial construction, capture/return handoffs, twenty arguments, deep calls,
  invalid roots, and collector scratch growth.

Use a frozen, capability-verified seed. Linux AMD64 and ptrace support are
required for the execution and syscall fault probes. Terminal test exits are
component harness signals; they are not public runtime diagnostic acceptance.

## Full-backend acceptance runners

Use the same frozen candidate with these runners; each creates a new evidence
directory and preserves prior runs.

- v160-native-scale-run.py --compiler A --fixtures DIRECTORY --output NEW_DIRECTORY
  checks the 34 frozen native scale cases, independent ELF geometry, exact runtime
  streams and input inventories. A failed or interrupted build remains Failed;
  later cells remain NotRun. A --skip run is partial evidence only.
- v160-scale-run-harness.py exercises pass, failure, timeout, changed input,
  late inventory failure and partial selection using controlled observations.
- v160-native-extended.py --compiler A --output NEW_DIRECTORY checks 40 control,
  lifetime, module order, relocation, identity and publication observations.
- v160-native-isolation.py --compiler A --userland ROOTFS --output NEW_DIRECTORY
  builds and runs 41 values with no host toolchain or compiler sources visible.
  It records the unchanged userland inventory and requires executable mode 0755.

The scale runner's 900-second build and 120-second runtime guards only bound
functional exploration. This runner does not adopt or measure formal budgets.

## v1.6 measurement matrix

The updated v160-native-scale.py reproduces all 34 frozen scale fixtures,
including the combined project and resource loop. Run v160-measure-fixtures.py
with --scale, --c0, --c1 and --output to freeze 103 measurement cells:
whole C0/C1 check/lower, scale lower/build, and native dynamic-input runs.
The C0 inventory and manifest must match the fixed reference corpus.

v160-measure.py takes --compiler, --scale, --c0, --c1, --manifest,
--seed-receipt and --output. It runs one fresh warm-up and three recorded runs
per selected cell, preserves raw streams and failures, checks input identity,
and records the environment at each start. Native cells require their measured
build cell to pass first. --only produces explicitly partial evidence.

The default 900-second / observed 4096-MiB cutoffs are preliminary bounds.
--formal-budget requires a separately adopted record bound to the exact
compiler, seed, source inventory and measurement manifest, with limits for
every cell. Partial selection is rejected for formal runs. The command does
not adopt budgets, and synthetic test budgets confer no adoption authority.
Cost counters, reclamation/fd observations, inherited budgets and complete
version acceptance remain separate gates.

Run v160-measure-harness.py, v160-budget-harness.py and
v160-measure-cli-harness.py (the latter takes the five fixture/seed inputs)
before measurements. These exercise real process cleanup and controlled
complete/partial matrices, invalid artifacts, failed warm-ups and late cutoffs.

v160-native-lifetime.py --compiler A --fixtures DIRECTORY --output NEW_DIRECTORY
records all 15 fixed-program lifetime and I/O input combinations. It preserves
heap/GC/fd observations, input/compiler/artifact identities and failed/unrun
cells. Resource leaks, unexpected exits and changed inputs fail the runner.
v160-lifetime-harness.py tests those rejection paths with controlled observations.
These observations do not set formal memory-growth or wall/RSS budgets.

The v1.6 wide-input regressions are v160-paged-index.py and
v160-wide-values.py. The former checks persistent table indexing against
sequential values and stale-index mutants. v160-review-flow.py and
v160-conformance.py retain the v1.5 sources with explicit N160 build migrations.
See verification/v1.6.0-wide-front-end.md for the bounded validation scope.

## Final regression and independence

Run v160-inherited-performance.py with --repository CHECKOUT --compiler A
--fixtures FROZEN_V150_FIXTURES --output NEW_EVIDENCE. It authenticates the
unchanged v1.5 budget and 118-cell input manifest, then applies those criteria
to the new A in fresh processes. It does not rewrite the original budget identity
or describe the observations as the original v1.5 formal run.

Run v160-whole-isolation.py with --repository CHECKOUT --compiler A
--userland MINIMAL_UBUNTU --c0 FIXED_C0 --c1 FINAL_C1 --output NEW_EVIDENCE.
Both whole corpora are mounted read-only; check and lower execute with only A,
the inputs and a minimal userland. Repeat for the two supported Ubuntu userlands.
The 900-second timeout is a functional guard, not a performance budget.

Run v160-review-runtime.py with --compiler A --output NEW_EVIDENCE to exercise
runtime-owned module captures, released parent closures and nested type/value
specializations under normal execution and forced collection.

The v160-try-review.mgn probe targets actual TrySite Err reconstruction with
distinct success types and String/product error payloads. It changes only the
constructor descriptor to the operand Result, omits exactly the canonical
allocation point (the projection of a false may-allocate claim; effects are
derived rather than mutable IR fields), and clears only the extracted payload
root. Both independent root validators reject the latter two corruptions.

Run v160-lower-driver.py with --compiler A --output NEW_EVIDENCE for lower CLI,
UTF-8/manifest failures, scalar locations and unreachable-source diagnostics.
Run v160-profile-boundaries.py with those arguments for 13 nominal-identity,
constructor, alias, generic and re-export cases across check/lower/build.
Run v160-stream-boundaries.py with those arguments for partial-read consumption,
short stdout/stderr writes and stream functions stored in a List under normal
execution and forced collection. Existing field/parameter cases remain in
v160-native-io.py.

Run v160_reclamation.py with --budget ADOPTED_BUDGET --observations LIFETIME_DIR
to validate all fifteen raw lifetime records and their artifacts against the
adopted memory-growth criteria. v160-reclamation-tests.py takes the same inputs
and exercises 21 corrupted records; these controls are separate from fresh
formal lifetime observations.
