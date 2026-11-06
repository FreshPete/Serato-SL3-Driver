# Local Windows instrumentation build investigation

The current Windows SL3 path needs local process instrumentation only. An offline build of pinned Frida 17.25.2 was configured with the local backend enabled and every nonlocal device backend disabled. The initial MSVC build failed; a separate verified Clang toolchain now reaches agent linking after small reviewed declaration fixes, but linking remains incomplete. No replacement runtime was imported, installed into the session kit or launched. The existing diagnostic hold remains in place. [Initial evidence](evidence/frida-local-build-20261106.json) · [Clang attempt](evidence/frida-local-clang-build-20261106.json)

This work follows the [Defender helper quarantine and passive captures](passive-action-capture.md). It does not establish that the quarantined file was harmless or that a different build will pass protection checks. No exclusion, quarantine restoration, signing change or protection disablement was made.

## Why configure the dependency

Upstream's default device manager initializes its compiled device backends before selecting a local device. The [host session service](https://github.com/frida/frida-core/blob/17.25.2/src/host-session-service.vala) and [build options](https://github.com/frida/frida-core/blob/17.25.2/meson.options) expose the relevant separation. The pinned core build files condition the Idun dependency and embedded helper on the Fruity backend. Disabling that unused Apple-device backend is a dependency-scope change for this Windows project, not a conclusion about antivirus compatibility.

The initial attempt used unchanged upstream sources at the commits in the evidence file. The inspector verifies those commits and refuses tracked modifications by default. Its explicit reviewed-change mode accepts only the exact additions described below. The generated configuration has 36 targets, no Idun target/dependency text, a local-backend compilation flag and no other backend compilation flags. That is evidence about build configuration, not an attestation of final embedded asset contents.

## Build recipe and observed failures

The initial configuration uses Python bindings only, with these Meson options after the configure wrapper's `--` separator:

```text
-Dfrida_python=enabled
-Dfrida_tools=disabled -Dfrida_node=disabled -Dfrida_net=disabled
-Dfrida_swift=disabled -Dfrida_qml=disabled
-Dgadget=disabled -Dserver=disabled -Dportal=disabled
-Dinject=disabled -Dgraft_tool=disabled
-Dfrida-core:local_backend=enabled
-Dfrida-core:fruity_backend=disabled -Dfrida-core:droidy_backend=disabled
-Dfrida-core:socket_backend=disabled -Dfrida-core:simmy_backend=disabled
-Dfrida-core:barebone_backend=disabled -Dfrida-core:compiler_backend=disabled
-Dfrida-core:tests=disabled -Dfrida-gum:tests=disabled
```

Reconfigure with `-Dfrida-core:compat=disabled` before compiling target `_frida`, to avoid an unnecessary secondary-architecture build. Run the pinned Meson entrypoint with a private build Python, `FRIDA_VERSION=17.25.2` and the compiler environment. The build Python uses setuptools 80.9.0, fetched from PyPI and hash checked against its package metadata. Upstream supplied toolchain/SDK version 20261030. These are build dependencies, not a replacement for the SL3 audio binaries.

The installed MSVC 19.29 compiler with Windows SDK 19041 initially failed on newer Windows API definitions. Microsoft's [SDK CPP package](https://www.nuget.org/packages/Microsoft.Windows.SDK.CPP/10.0.26100.1) and corresponding [x64 libraries](https://www.nuget.org/packages/Microsoft.Windows.SDK.CPP.x64/10.0.26100.1) were downloaded and each passed `dotnet nuget verify --all`. Extraction stayed under the project's ignored artifacts directory; nothing was installed system-wide.

Using the newer UCRT produced an unresolved guard-runtime symbol with the installed compiler. A clean rebuild retained the installed UCRT and prepended only the newer `um/shared` headers and `um/x64` libraries. It passed the earlier API-definition failures, then stopped because this compiler rejects empty aggregate initializers in upstream `xnu-syscalls-glue.c`. No source substitution, guessed API declarations or guard-symbol suppression was applied. All three terminal failure logs are preserved locally and hash bound by the evidence file.

That initial attempt needed a newer compiler; the next section records the separate toolchain attempt. Compilation success would still require static dependency/asset review and a separately scoped runtime test under unchanged protection before updating a session package.

## Project-local Clang attempt

The official [LLVM 21.1.8 release](https://github.com/llvm/llvm-project/releases/tag/llvmorg-21.1.8) provides a Windows x64 archive. Its downloaded SHA-256 matched the release asset digest, and GPG verified its detached signature using the key obtained from LLVM's official release-key page. The signer fingerprint and hashes are retained in the evidence. This establishes the signature against that published key; no independent web-of-trust certification is claimed. The keyring, compiler and extracted resources stay under ignored project artifacts, with no system installation or global PATH change.

Clang and LLD 21.1.8 were selected through an explicit Meson native file in a fresh build directory. The upstream configure wrapper's compiler probe fell back to a stale Visual Studio Enterprise path on this host. Direct native-file configuration avoids that discovery failure and still uses the same source pins, SDK dependencies and local-only options. Windows SDK 26100 `um/shared` headers and `um/x64` libraries are prepended, retaining the installed MSVC headers/UCRT. This mixed toolchain is an experiment, not a supported release configuration.

Clang's implicit-function errors exposed three missing Gum includes. The [Gum patch](../patches/frida-gum-17.25.2-windows-includes.patch) adds the existing headers declaring module enumeration, destructor registration and Windows context conversion. The [core patch](../patches/frida-core-17.25.2-windows-agent-declarations.patch) adds two `_MSC_VER`-guarded `void (void)` declarations matching the definitions of the libc-shim initialization/deinitialization functions. Both patches passed reverse-apply checks against the private checkout. No implementation body was changed and no implicit-declaration diagnostic was suppressed.

With those changes, the build reaches linking of `libfrida-agent-raw.dll`. It stops on an unresolved `__writegsqword` TLS intrinsic and newer Microsoft STL helper symbols referenced by the prebuilt V8 library. Those failures remain unresolved. No substitute symbol definitions, TLS algorithm change or engine selection change was made. QuickJS and V8 retain the upstream configured settings in this attempt.

The next step is to resolve the complete compiler/runtime combination, or separately review and test the specific remaining portability/dependency changes. A successful compile alone will not prove runtime or antivirus compatibility. The session package and its existing audio binaries remain unchanged; a post-build read-only recovery check still reports original Serato resources and no temporary registration.

## Nonexecuting inspection

The original helper [inspect-frida-local-build.py](../scripts/inspect-frida-local-build.py) checks source pins, tracked cleanliness, required Meson options, target metadata and generated compilation flags. `--configuration-only` explicitly skips candidate inspection. `--allow-reviewed-windows-includes` additionally permits only the three exact include additions and two exact agent declarations encoded in the inspector; all other tracked changes are refused. Its report includes original and normalized patched file hashes. Without configuration-only mode it requires the built `_frida.pyd` and uses `pefile` to read its AMD64 image, Python entry export and stable-ABI dependency as data. It never imports the candidate. Eighteen tests cover configuration rejection and exact patch acceptance/refusal, including wrong declarations and extra implementation edits. These tests do not prove runtime behaviour.

No rebuilt candidate exists yet. The audio package is unchanged, and no new hardware, DVS or clean-shutdown validation is claimed here.
