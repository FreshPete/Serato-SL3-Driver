# Artifacts and provenance

Inventory date: 26 October 2026. Vendor binaries stay outside Git. Full SHA-256/size/header records: [file inventory](evidence/artifact-files.json); network retrieval records: [download ledger](evidence/downloads.jsonl).

## Original packages

The current Rane catalogue omits SL3. Links were recovered from the [archived official legacy downloads page](https://web.archive.org/web/20240622230737id_/https://www.rane.com/downloads-legacy.html), then downloaded directly from inMusic. These are the latest SL3 legacy packages located in that official catalogue; no claim of an exhaustive vendor release history is made.

| Package | Version | Bytes | SHA-256 |
| --- | --- | --- | --- |
| [Sl3-2.0.1f2.zip](https://cdn.inmusicbrands.com/rane/legacy-product-downloads/Sl3-2.0.1f2.zip) | 2.0.1f2 Mac | 228447 | `e6558b7d8c95148a9629a0c2a70dfb8e4dd0351fb03c43b158304a08f1617264` |
| [RaneAsioSl3Ver1.3.5f2.zip](https://cdn.inmusicbrands.com/rane/legacy-product-downloads/RaneAsioSl3Ver1.3.5f2.zip) | 1.3.5f2 Windows | 8451356 | `6a21aeb31900a543b1a0ee08094af8067833fda79c701c6429cbd926606c2b12` |

Windows installer `RaneAsioSl3Setup.exe`: SHA-256 `7c4dcfed4d64f42159cfe2a11adbb4cb125ed764fa4932ef72b535e673478f6b`, 8,522,536 bytes, Rane Corporation Authenticode valid. Its product is 1.3.5f2; INF DriverVer and file-resource version are distinct identifiers.

## Serato Windows installers

The owner downloaded/provided these installers locally during this session. Network transfer URLs were not independently captured, so provenance is owner-provided plus verified Serato Limited Authenticode, not an invented retrieval record. Official release pages: [2.5.5](https://serato.com/dj/pro/downloads/2.5.5), [2.5.6](https://serato.com/dj/pro/downloads/2.5.6), [current stable 5.0.0](https://serato.com/dj/pro/downloads). The current version was independently checked on the official page when work began.

| Installer | MSI product version | Bytes | SHA-256 |
| --- | --- | --- | --- |
| Serato DJ Pro 2.5.5.83_64bit_Installer.exe | 2.5.5.83 | 723834912 | `bfade04e499b734127398f951fe83fae68eca3cc56d5284e4da15da2d8938958` |
| Serato DJ Pro 2.5.6.exe | 2.5.6.1001 | 789139488 | `3d5e44c6e8e775f3854d754980a80b32fa4f569a68592a5fc249288b9c255b56` |
| Serato DJ Pro 5.0.0.exe | 5.0.0.1278 | 1774279752 | `653e8027cf15cfeae324818b1b68bf08b04c4d811bbd20d18af2a5c2394d2ff8` |

All three installers verified as signed by Serato Limited. Main application identities:

| Executable version | SHA-256 |
| --- | --- |
| 2.5.5.83 | `ba8641d0329fe0c955147d2b45f247eeea82ac0f812fe30a339834dbe0c0a503` |
| 2.5.6.1001 | `3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5` |
| 5.0.0.1278 | `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265` |

The installed 5.0.0 executable matches the extracted hash. Historical packages were not installed. Main MSI LaunchConditions are `Installed OR (VersionNT64 >= 601)` in 2.5.5 and `>= 602` in 5.0.0; these application checks are not the Rane driver installer checks.

### Current Mac application artifact still missing — checked 27 October 2026

The current [official 5.0.0 release page](https://serato.com/dj/pro/downloads/5.0.0) advertises the Mac installer. Fresh first-party page metadata identifies **`Serato DJ Pro 5.0.0.pkg`**, **1,051,590,750 bytes**, public resource ID **156199**, type `mac-installer`. This is metadata only; no installer bytes, SHA-256 or signature have been acquired for that package.

The normal anonymous installer POST returned HTTP 403. The existing signed-in browser showed its logout control, but the actual Mac installer link still left “Something went wrong” visible and no download appeared in the checked project/download locations. Its underlying HTTP result was not independently verified; do not equate the UI error with the anonymous API response or infer an account/license cause. Credentials, cookies and tokens were not extracted or copied; no CDN URL guessing, alternative mirror or authentication automation was used. [Bounded request/page metadata evidence](evidence/serato-mac500-download-check.json).

The precise artifact needed for further Mac application analysis is the official PKG above. Older cached metadata is not a replacement for the current installer. Receiving it would permit extraction and architecture-specific inspection on this host; Mac execution/signature admission and Core Audio/DVS still require the actual target.

## Relevant extracted x64 files

| File | Bytes | SHA-256 |
| --- | --- | --- |
| RaneAsioSL3.dll | 2683280 | `e3d88039547b70915b1a9bc9e3e3f7dba32aaa9bc3ce8fd51616565ea1734141` |
| strmdrv.cat | 8502 | `3169df3e2fcd8041a089f432d2cd04f05f93eb20bced840dfc5e68ee844e7986` |
| strmdrv.inf | 2857 | `7191f7c6fd5fda7503eb9eabee2522868a9d1f2ddd766fe6dc9145d6c69e8f76` |
| strmdrv.sys | 36240 | `e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5` |

SYS/INF catalogue membership verified using SDK SignTool `/kp /v /c`; both succeed with a timestamp warning. Runtime CI subsequently rejects the unchanged installed SYS, whose flat hash matches the extracted x64 copy. Keep offline signature validity distinct from current load-policy admission. See [kernel check](evidence/strmdrv-kernel-signature.txt), [INF check](evidence/strmdrv-inf-signature.txt), [file signatures](evidence/rane-windows-signatures.json), and [runtime CI fields](evidence/code-integrity-driver-fields.json).

Mac package signatures are not yet validated with Apple tools. Architecture/dependency evidence is in [Mach-O report](evidence/rane-mac-macho.json). Windows package extraction did not execute Mac scripts.

## Research and tools

- Supplied `Rane_SL3_Compatibility_Plan.docx`: retained under docs, identity in [plan record](evidence/plan-identity.json). Read XML text, all table cells and external reference relationships. Its mandatory Windows 10 sequence is superseded by the owner’s instructions.
- Linux research: `nvgeele/snd-rane-sl3`, commit `01099892261b55ec5ee814292d840eeb664c1904`, GPL-3.0. Local checkout ignored under tools; no source reused.
- REA official project: https://github.com/morluto/rea and https://rea.tools/ . Executed npm package `rea-agents@6.8.0`; isolated under tools/rea.
- Node 24.22.1, Ghidra 12.1.4, Temurin 21.0.9+10 and innoextract 1.9 download URLs and hashes are recorded in the ledger.
- PE readers: pefile 2024.8.26; Capstone 5.0.9 in the project venv.
- Microsoft WDK NuGet x64 10.0.28000.2526: 113,683,738 bytes; SHA-256 `63c939fb5a79295bf40e941db592681272219b04edff095fe2f3d123e5579a90`. Official NuGet URL is in the download ledger; Microsoft author and repository signature verification passes. Extracted project-local Inf2Cat generates the experimental WinUSB catalogue with zero errors/warnings. Its individual Authenticode check reports UnknownError; see [workflow and limits](analysis-workflow.md). No system-wide WDK/VS install occurred.
- Original experimental WinUSB INF: `src/windows/sl3winusb.inf`; unsigned generated package under ignored `artifacts/build/sl3winusb`. [Build hashes and signature status](evidence/winusb-package-build.json). This is not a downloaded Rane component or a signed release.

## Acquisition gaps

No required Windows installer is now missing. The Rane Mac package is acquired. Mac Serato installers and a Mac test host have not been acquired/tested in this first Windows-focused session. A usable Microsoft-signed legacy SL3 kernel package has not been located. Do not replace missing evidence with mirror version labels or simulated load tests.
