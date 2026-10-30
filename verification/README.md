# Verification

The accepted [1.5 Lisp capability](v1.5.0-lisp.md) supplies path inspection.
The accepted [replacement seed](v1.5.0-seed2.md) bootstraps the
[1.5 compiler implementation](v1.5.0-compiler.md); source and artifact identities
are fixed by the [final acceptance and release record](v1.5.0-release.md).

The retained [1.4.0 acceptance](v1.4.0.md) records complete-source parsing, shared
frontend native continuity, [54 new conditions](v1.4.0-conformance.md), 55 inherited
conditions and [all formal resource samples](v1.4.0-performance.md). Its
`python3 tests/mgnc/acceptance.py` command checks the pinned 1.4 evidence and
source identities from that historical checkout; it is not the 1.5 completion gate.
Implementation acceptance does not authorize release publication.

The retained [1.3.0 review corrections](v1.3.0-review.md) record all 55 conditions,
63 additional regressions and a complete resource rerun with a fixed source/seed.
The [initial acceptance](v1.3.0.md) and [resource results](v1.3.0-performance.md)
remain available as historical evidence.

The [1.2.0 implementation progress](v1.2.0-progress.md) records unreleased increments and remaining work.

The [1.1.0 native runtime record](v1.1.0-runtime.md) describes the free-list,
worklist, independent membership index, and their verification boundaries.

The [v0.14 review corrections](v0.14.0-review.md) cover first file close,
scalar root lifetime, and primary-phase guard verification.

The retained 1.1.0 implementation record is [v1.1.0](v1.1.0.md), with complete
[performance samples](v1.1.0-measurements.json). The retained [v0.14.0 record](v0.14.0.md) has its
[coverage ledger](v0.14.0-conformance.md). The inherited [v0.13.0 record](v0.13.0.md)
has a [42-condition ledger](v0.13.0-conformance.md) and [internal gates](v0.13.0-internals.md).
The [v0.13 review corrections](v0.13.0-review.md) cover directory mmap errno
classification and independent verification of internal-failure latch paths.
The [v0.12 review corrections](v0.12.0-review.md) cover repeated stdin consumption
and primary failure preservation across diagnostic and signal cleanup paths.
The retained v0.11 [72-case ledger](v0.11.0-testing.md) and
[process evidence](v0.11.0-process.md) describe the inherited runner.
The [runner review fixes](v0.11.0-review.md) cover host storage recovery,
helper frame-register preservation, and committed-result diagnostics.
The current accepted compiler release record is
[v1.7.0](v1.7.0-release.md); publication is established by its signed release.
The prior release record is [v1.6.0](v1.6.0-release.md).
The retained stable release record is [v1.0.0](v1.0.0-release.md).
The retained source release record is [v0.14.0](v0.14.0-release.md).
Run checks from the repository root on a non-root Linux amd64 host with SBCL,
Python 3, glibc 2.34+, strace, getfacl/setfacl, and permission to trace child processes. The v0.13 different-group inheritance
fixture additionally requires membership in a supplementary group distinct
from the process effective GID; the owned fixture directory is assigned to it.

```sh
sbcl --noinform --script scripts/test.lisp
git diff --check
sha256sum -c verification/SHA256SUMS
```

[Test coverage](../tests/README.md) describes the active ASDF suite, migration,
independent oracles, and resource probes. Each failed assertion fails the run.

## CLI and native checks

```sh
./bin/mgn run examples/modules/mognitio.toml
./bin/mgn build examples/modules/mognitio.toml -o example
./example
```

All three commands succeed silently with exit 0. The suite checks ELF fields, standalone execution, deterministic
cold/warm caches, relocation, paths, and failures before and during publication.

Determinism uses source bytes, target, and compiler build identity.
Record the exact revision, manifest, SBCL/ASDF versions, and internal test options.
The [manifest](SHA256SUMS) covers delivered files except itself; it identifies
contents rather than proving that tests passed.

## Repository review

The [v1.7 implementation review map](v1.7.0-review.md) identifies the current
source, completed acceptance evidence and the release-review boundary.

Include new files in review. Check changed Markdown links and fences, UTF-8,
LF endings, final newlines, executable launchers, and whitespace.
Follow [contribution guidelines](../CONTRIBUTING.md) and publish sanitized
evidence. Do not include private setup details in public records.

## Historical records

- [v0.13.0 release](v0.13.0-release.md)

- [v0.12.0 release](v0.12.0-release.md)
- [v0.11.0 release](v0.11.0-release.md)

- [v0.10.0 release](v0.10.0-release.md)
- [v0.9.0 initial source increment](v0.9.0-progress.md)
- [v0.8.1 release](v0.8.1-release.md)
- [v0.8.0 implementation](v0.8.0.md) and [release](v0.8.0-release.md)
- [v0.7.0 implementation](v0.7.0.md), [review](v0.7.0-review.md), and [release](v0.7.0-release.md)
- [v0.6.0](v0.6.0.md), [v0.5.0](v0.5.0.md), [v0.4.1](v0.4.1.md)
- [v0.4.0](v0.4.0.md), [v0.3.0](v0.3.0.md), [v0.2.0](v0.2.0.md)

Historical counts and old source oracles apply to their pinned revisions.
Historical branch completion does not authorize a release tag or publication.

- [v0.15.1 package permissions](v0.15.1.md): archive modes and non-owner execution regression.

- [1.4.0 review correction](v1.4.0-review.md): native argument classification, exact combined depth and fresh acceptance evidence.

- [v1.5 internal seed](v1.5.0-seed.md): accepted Lisp source, frozen bundle identity and isolated restoration.

- [v1.5 replacement seed](v1.5.0-seed2.md): accepted GC repair with a new immutable seed identity.
- [v1.5 compiler implementation](v1.5.0-compiler.md): shared semantics and fixed-candidate verification.

- [v1.5 flow review correction](v1.5.0-review-flow.md): unique Unknown operators and module initializer reachability.

- [v1.5 corrected-candidate performance](v1.5.0-performance.md): complete preliminary and inherited parse reruns.

- [v1.5 formal semantic performance](v1.5.0-formal-performance.md): adopted budgets, complete formal run and harness validation.

- [v1.5 wall-cutoff correction](v1.5.0-wall-cutoff.md): delayed-reap regression and saved formal-run revalidation.

- [Small allocation search cursors](v1.6.0-fit-cursors.md): first-fit preserving search reuse for compiler-scale workloads.

- [v1.6 replacement bootstrap seed](v1.6.0-seed3.md): immutable replacement identity and capability evidence.

- [v1.6 large-live-heap arena growth](v1.6.0-arena-growth.md): reserve policy and independent collection-count regression.

- [v1.6 adaptive-growth bootstrap seed](v1.6.0-seed4.md): current immutable bootstrap and capability evidence.

- [v1.6 whole-project lowering](v1.6.0-whole-ir.md): complete-source IR, independent verifier and corpus evidence.

- [v1.6 native planning](v1.6.0-native-planning.md): concrete instances, closure environments and independent mutation checks.

The [1.6 generated runtime components](v1.6.0-runtime-components.md) record
independent root/layout checks, physical-heap execution and ABI probes.

The [1.6 scale preparation](v1.6.0-native-scale.md) records independent root
reachability, bounded source splitting, Unicode equivalence and the remaining
whole-project cutoff.

- [Two-way exact-size allocator cursors](v1.7.0-two-way-fit-cursors.md): first-fit correctness, collision bounds and replacement-seed boundary.

- [Bounded reserve for large native heaps](v1.7.0-adaptive-reserve.md): unsigned policy boundaries, native collection controls and replacement-seed boundary.

The [large-heap reserve seed](v1.7.0-seed-adaptive-reserve.md) records the new
immutable bootstrap prerequisite and its qualification boundaries.

[Bounded backend work](v1.7.0-backend-work.md) records relative ownership keys,
buffered encoding and their independent regression controls.

[First-fit search bounds](v1.7.0-fit-lower-bounds.md) documents safe reuse across
different requested sizes and its independent equivalence/work controls.

The [first-fit-bound seed](v1.7.0-seed-fit-lower-bounds.md) records the new
immutable bootstrap prerequisite and its qualification boundaries.

[Bounded machine-verifier ranges](v1.7.0-machine-range.md) preserves selected bytes
and bounds allocation work for short slices of large lists.

[Balanced pending encoding fragments](v1.7.0-balanced-encode-buffer.md) bounds
repeated prefix copies while preserving emitted bytes and carry order.

The [bounded exit observation](v1.7.0-observation-exit.md) handles large-heap teardown and retains wall/RSS cutoffs.

- [Wider persistent radix map](v1.7.0-wide-radix-map.md): expanded label-key range, snapshot equivalence, allocation bounds, and forced collection.

[Capture verification allocation](v1.7.0-capture-check.md) preserves independent
capture and module-load checks while avoiding read-only list copies.

The [repeated generation evidence foundation](v1.8.0-evidence-foundation.md)
provides immutable producer records, isolated generation and fresh observations.
Its focused controls do not establish whole-version acceptance.

[Native allocator first-fit cursors](v1.8.0-native-fit-cursors.md) preserves
ordered selection while bounding repeated free-prefix scans in emitted runtimes.

[Generation candidate preconditions](v1.8.0-generation-preconditions.md) binds
runtime inventories, target identity and the actual generation policy before execution.

[Bounded native mark searches](v1.8.0-native-mark-search.md) preserves pointer
validation while avoiding repeated static and arena searches for heap references.

[Adaptive native arena capacity](v1.8.0-native-arena-capacity.md) scales uncapped
large-heap growth while preserving collection order and capped geometry.

[Fitting reserve after native collection](v1.8.0-post-collection-reserve.md)
prevents small reclaimed tails from suppressing optional arena growth.

[Reachable semantic parse forests](v1.8.0-semantic-forest-retention.md)
reduces retained parser data while preserving every completed syntax alternative.

[Short pruning memo paths](v1.8.0-prune-memo.md) reduce small-node radix work
while preserving shared forests and the full nonnegative integer key range.

[Machine-record page iteration](v1.8.0-record-page-iteration.md) avoids per-page
iterator buffers while preserving verifier diagnostics and complete ELF bytes.

[Compiler traversal allocation lifetime](v1.8.0-allocation-lifetime.md) records
compact pruning frames, the separate reserve trigger and indexed chunk merging.
