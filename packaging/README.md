# Linux toolchain distribution

Mognitio 1.9 packages use the same verified native compiler for the CLI, test
runner, and language server. Both Ubuntu 24.04 and 26.04 amd64 use CPython
3.12 or later, glibc, libstdc++, and util-linux. The qualified Lisp seed is a
build input for the first compiler generation.

## Build the 2.0.0-alpha candidate

Use Linux amd64, Python 3.12 or later and the signed 1.9.0 release bundle.
Verify the release manifest and its artifacts as described below. The alpha
bootstrap checks the pinned archive, manifest, compiler and host adapter
before using the native seed. From a checkout of the candidate, choose new
sibling output directories and run

    python3 -IB scripts/build-alpha-toolchain.py \
        --seed-archive "$RELEASE/mognitio-1.9.0-linux-amd64.tar.gz" \
        --seed-manifest "$RELEASE/manifest.json" --graph "$BUILD/graph" \
        --output "$BUILD/payload"

The graph records frozen source inputs and the Compiler A generation. The
payload contains the paired CLI, runner, language server and compiler. Run
`"$BUILD/payload/bin/mgn" --version` to confirm the selected candidate. An
independent generation from the same source and seed can be compared using
the compiler hashes and modes in the two `generation.json` files. Official
distribution packages continue to require a verified release-mode build.

## Build an immutable 1.9 payload

From a clean checkout, set GRAPH to a fresh build directory, SEED_RECEIPT and
SEED_ARCHIVE to the verified 1.8 seed receipt and archive, and HOST_BUILD to
a directory on the build filesystem. ASMJIT_SOURCE and PYTHON_HEADERS identify
the exact upstream archives in [the native host lock](native-host-lock.json).
The host builder checks the input hashes, compiler version, and output digest.

    python3 -IB tools/selfhost/freeze.py "$GRAPH/inputs" --mode release --seed-receipt "$SEED_RECEIPT"
    python3 -IB "$GRAPH/inputs/tools/selfhost/bootstrap.py" "$GRAPH" --seed-archive "$SEED_ARCHIVE"
    python3 -IB "$GRAPH/inputs/scripts/build-native-host.py" --asmjit-source "$ASMJIT_SOURCE" --python-headers "$PYTHON_HEADERS" --output "$HOST_BUILD/_application.abi3.so"
    python3 -IB "$GRAPH/inputs/scripts/build-native-toolchain.py" "$GRAPH" --output "$HOST_BUILD/payload" --host-adapter "$HOST_BUILD/_application.abi3.so"
    python3 -IB "$GRAPH/inputs/scripts/package-toolchain.py" "$HOST_BUILD/payload" --output "$HOST_BUILD/packages"

Bootstrap generates A, B, an independent B repeat, C, and an independent C
repeat. Packaging verifies the raw fixed point and embeds B. The native host
adapter lets an ordinary run honor an inherited file-size limit throughout
compilation and program execution. See [the build lock](build-lock.json)
for the historical saved-core inputs used with releases through 1.8.

The installed tools accept --version. The language server accepts --stdio.
The source checkout's bin/mgn is the contributor bootstrap.

## Package and verify

Run scripts/package-toolchain.py PAYLOAD --output OUTPUT to create a Debian
package, offline archive, and manifest.json from one verified release payload.
The Debian revision is separate from the upstream toolchain version.
Packaging exports directories as 0755, executable files as 0755, and data as
0644, regardless of the build umask or private staging directory modes. The
source payload remains unchanged. Validate system packages as an unprivileged
user after root installation; execution as the installing root user is not
sufficient to detect inaccessible payload directories.

Sign the manifest with the independently managed bundle signing subkey.
Before extracting or executing an offline installer, use scripts/verify-bundle.py
with --manifest, --signature, --keyring, and --fingerprint. Obtain the public key
and full fingerprint from the reviewed [APT key record](https://github.com/ProjectCuriositas/apt#production-public-key);
a key supplied by the archive itself is not sufficient trust. GitHub and Pages
share an account authority; an independent trust channel is not yet available.
This checks signature and artifact hashes, not current revocation status.
Refresh trust information before installing; stale offline keyrings cannot
establish that a key has not since been revoked.

No production signing key, repository URL, or official release is created by
these scripts. Do not substitute test keys or fixture URLs into public setup
instructions.

## Offline user installation

After external verification, extract the archive, then run its install.sh with
--prefix PATH. The default is ~/.local; do not use sudo. --version VERSION
requires the exact formal version contained in the bundle. Both programs are
exposed under PREFIX/bin, which the installer prints for PATH setup.

The installer locks the prefix, validates payload and ownership, stages an
immutable generation, and atomically switches the active generation. Interrupted
operations are recovered on the next invocation. Repeating the same verified
version is a no-op; downgrades and a different build of the same version are
rejected. Previous generations are retained for existing processes.

Use the printed PREFIX/lib/mognitio/uninstall.sh command even after removing the
downloaded archive. Only unchanged recorded files are removed. Modified files
and unrelated user data are retained; partial removal returns status 2.
Do not manually replace managed files or ownership metadata.

## APT staging

scripts/apt-repository.py --output NEW_DIRECTORY --signing-key APT_SUBKEY DEB...
creates a signed stable/main amd64 repository tree. It requires dpkg-scanpackages,
apt-ftparchive, and GnuPG. Use a signing subkey separate from bundle signing.
The script stages files without uploading them.

The official repository must be published and its key independently authenticated
before users can register it with signed-by and run sudo apt install mognitio.
APT verifies signed repository metadata and package hashes. Do not use trusted=yes
or allow-unauthenticated. Removing or purging this package leaves user projects
and independently installed user-prefix toolchains intact.

A language server session retains its verified payload so it can reanalyze after
APT reclaims an older installation. Restart the server to select a new toolchain.
The selected executable path determines the running version; another mgn on PATH
may belong to a different installation.

## Release signing environment

An owner registers the separately exported encrypted bundle subkey with
scripts/register-bundle-key.py /path/to/online-transfer after checking the public
fingerprints against the offline record. Enter the passphrase in the local
terminal only. The script rejects primary secret material and other subkeys,
verifies the passphrase through a temporary signature, and registers only
BUNDLE_SIGNING_KEY and BUNDLE_SIGNING_PASSPHRASE in the release-signing environment.

Prepare immutable draft release assets and record manifest.json's SHA-256.
Dispatch the Sign frozen release manifest workflow on main with that digest.
The version tag must name the exact main commit. The workflow verifies the
frozen artifact set and attaches only manifest.json.asc to the draft; publishing
the release is a separate action after final verification.
