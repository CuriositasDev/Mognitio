# Experimental native compiler

This source project implements the Mognitio 1.5 compiler, mgnc.
It remains experimental and is not included in the regular Debian package,
APT repository, or installer bundle. Implementation, final acceptance,
performance-budget adoption, and release are separate stages.

## Build

Use the [replacement frozen v1.5 Lisp seed](../../verification/v1.5.0-seed2.md), whose accepted
source revision is 860a7550cb610e3a60642e427db659df7447fcf5.
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
/new/output/mgnc build path/to/source.mgn -o path/to/new-artifact
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

Build consumes the same complete semantic result, then selects the existing
native subset: a single file with typed scalar helpers and main, direct calls,
blocks, mutable locals, branches, while loops, and checked signed arithmetic.
Main takes List<String> and returns Int; direct argument-length queries are
supported. Semantically valid features outside this subset report unsupported.
Contract, witness, attribute, and assertion syntax remain outside mgnc's
experimental profile; the normal toolchain continues to support them.

Successful compiler commands have exit 0 and empty output streams.
Build publishes a new standalone Linux AMD64 ELF without replacing an existing
output. It does not invoke a fallback compiler or run the generated program.
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
