# Experimental native compiler

This source project extends the accepted Mognitio 1.6 experimental compiler
toward 1.7. The current increments add native assertions, normal-build `@test`
metadata, named witness checking with typed whole IR, and fixed-width scalar
arithmetic and numeric Result generation; complete 1.7
implementation and performance acceptance remain pending.
Final 1.6 conformance and performance acceptance are complete; see the
[acceptance record](../../verification/v1.6.0-final-acceptance.md).
It remains experimental and is not included in the regular Debian package,
APT repository, or installer bundle. All 1.6 implementation and performance stages are accepted; see the
[acceptance and release record](../../verification/v1.6.0-release.md).

## Build

Use the [qualified replacement Lisp seed](../../verification/v1.7.0-seed.md), whose accepted
source revision is 63c99a21cd50e31f458c83231c34adbdce3bf4f2.
Verify its complete component inventory and external receipt before invoking
the launcher by an explicit path:

~~~sh
python3 scripts/freeze-seed.py --verify /path/to/verified-seed
/path/to/verified-seed/bin/mgn build compiler/mgnc/mognitio.toml -o /new/output/mgnc
~~~

The existing frozen bundle must not be regenerated or replaced silently.

## Use

~~~sh
/new/output/mgnc parse path/to/source.mgn
/new/output/mgnc check path/to/source.mgn
/new/output/mgnc check path/to/mognitio.toml
/new/output/mgnc lower path/to/source.mgn
/new/output/mgnc lower path/to/mognitio.toml
/new/output/mgnc build path/to/source.mgn -o path/to/new-artifact
/new/output/mgnc build path/to/mognitio.toml -o path/to/new-project-artifact
path/to/new-artifact argument
~~~

Parse checks one complete UTF-8 file through EOF without resolving names,
opening imports, checking types, or writing artifacts.

Check validates the complete semantic profile, including nominal Product/Sum
types, aliases, templates, type/value arguments, standard signatures, captures,
control flow, and entry types. A project check includes every eligible source,
including unused modules and bodies. Project input rejects symlink entries and
duplicate file identities according to the v1.5 input-protection contract.
Check does not evaluate initializers, execute main, or write output files.

Lower transforms the complete semantic result into typed slot operations and
control-flow graphs, including unused bodies, nested functions, templates and
unreachable operands. Independent checks cover source membership, resolved
identities, operand order, lexical captures, definite assignment, current-value
variant guards and owner-typed Result reconstruction. Lower accepts the same
single-file and project inputs as check and neither evaluates user code nor
writes an artifact. The [final acceptance record](../../verification/v1.6.0-final-acceptance.md)
records complete-corpus, native backend and performance validation separately.

Build lowers the complete semantic result and selects the closed native profile
for single files and manifests. It supports Int, Bool, Unit, String, persistent
List, nominal Product/Sum, Result, concrete templates, function values, lexical
captures, value/control loops and the five text I/O functions readTextFile,
writeTextFile, readStdin, writeStdout and writeStderr. Main receives ordinary
List<String> argument values and returns Int. The generated runtime manages
reachable values and initializes entry-reachable modules once in dependency order.
Excluded standard identities and semantically valid features outside the native
profile report unsupported, including in unused bodies.

Fixed-width integers and Bits use raw scalar words, including the unsigned
upper half at width 64. Checked arithmetic preserves width and signedness;
bitwise operations, length and integer/bit reinterpretation preserve canonical
words across calls, captures and containers. Signed/Unsigned marker values keep
their ordinary Product representation. Conversion, checked bit shifts and bit access return ordinary typed Results;
errors preserve their nominal type and count/width fields. Their error object
remains rooted while the enclosing Result is allocated. Bytes and filesystem
additions remain gated until their runtime paths are ready.

Assertions require Bool on normally completing operands and preserve non-completing
control transfers. A failed assertion exits 5 with the original statement location;
ordinary return 5 is silent, and an operand panic retains its panic diagnostic.
`@test` metadata belongs to module-level immutable declarations. The normal
initializer executes once in each reachable module; the test body is not called
automatically and no test command or summary is added. Unknown, duplicate,
misplaced or incorrectly typed attributes are rejected by shared checking.
Named contracts and witnesses are checked throughout the project, including unused
and unreachable files. Packaging requires a local witness declaration or an
explicitly imported public witness; dispatch of a packed value requires neither
the concrete type nor its witness import. Witness bodies remain isolated from
outer runtime values. Check and lower preserve these bindings and method order.
Build reports unsupported for contracts and witnesses until native package and
dispatch support is complete.

Successful compiler commands have exit 0 and empty output streams.
Build publishes a new standalone Linux AMD64 ELF without replacing an existing
output. Manifest builds also protect the next source set from new .mgn output
members. It does not invoke a fallback compiler or run the generated program.
The native runtime validates UTF-8 arguments and preserves primary failures
when its diagnostic stream is unavailable.

Internal and end-to-end runners are under tests/mgnc. The historical
[1.4 acceptance](../../verification/v1.4.0-review.md) remains tied to its original
candidate; current v1.5 checks do not rewrite that evidence.
The compiler uses only public seed language/library facilities, including
inspectPath. No seed-private runtime symbol is called.

Original implementation evidence is recorded in [v1.5 compiler verification](../../verification/v1.5.0-compiler.md).
The [flow review correction](../../verification/v1.5.0-review-flow.md) records the
updated source/artifact identity and regression results.
