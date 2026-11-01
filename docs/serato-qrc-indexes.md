# Current Serato Qt resource discovery scope

Read-only inspection now covers the nine external Qt resource bundles registered by the current application's QRC setup and eleven explicit embedded registration sites. Their indexes contain **7,844 external and 332 embedded file entries**. None is under `userio`, `userio_partner` or `userio_hidden_from_partners`; none has an SL3 filename under the checked normalization. This narrows an additional descriptor-discovery candidate beyond the independently decoded [userio archive](serato-resource-container.md). It does not establish absence from every provider or every payload. [Checked metadata](evidence/serato500-qrc-indexes.json).

Target remains the unchanged installed/extracted Serato DJ Pro 5.0.0.1278 executable, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Each of the nine installed bundles exactly matches its pinned extracted original. Vendor code is never loaded or executed. No resource is modified, repacked or installed; payload contents and resource keys are absent from the report.

## Inputs and registration boundary

| External Qt bundle | Indexed files | Root |
| --- | ---: | --- |
| sdj_variant_resources.bin | 46 | modules |
| dj_resources_common.bin | 2,964 | modules |
| dj_resources_fonts.bin | 10 | fonts |
| dj_resources_html.bin | 1 | html |
| dj_resources_dark.bin | 3,266 | legacy_gui_resource |
| dj_resources_light.bin | 1,470 | legacy_gui_resource |
| dj_resources_scratch_live.bin | 65 | legacy_gui_resource |
| dj_resources_shaders.bin | 8 | Metal_Shaders |
| dj_resources_localization.bin | 14 | localization |

Original PE instructions verify nine setup calls to `140b0c3f0`, its registration helper `140b0c250`, resource loading helper `140b0ddf0`, the already recovered transform at `141cc6030` and the actual Qt buffer-registration import. Decoding these pinned inputs yields format-v3 Qt bundles. This application-data decoding is separate from device or account authentication.

Eleven selected embedded call sites pass format 3 and original PE addresses for tree, names and payload arrays through thunk `141b87910` to the actual `qRegisterResourceData` import. Their reachable indexes contain shaders, emoji and Qt assets. Their preferred-image addresses, entry counts and index digests are recorded. These are listed direct-call sites, not a claim of exhaustive recovery of every indirect registration or linked module's resources.

The common bundle contains `/modules/Common/UserIO.qml`. A UI filename containing “UserIO” is recorded separately from membership in a device-description folder. The parser does not treat it as a controller descriptor. No member payload XML was interpreted by this index inspection; payloads with unrelated names remain outside its identity-search scope.

## Independent index checks

The reader implements the format-v3 index layout described by [Qt's resource implementation](https://github.com/qt/qtbase/blob/v6.5.3/src/corelib/io/qresource.cpp), using big-endian fields, 22-byte nodes and UTF-16 names. That reference explains the format; it does not identify the application's exact Qt build. File payload lengths are bounded, but compressed contents stay opaque.

It validates header/section ordering, supported flags, node/name/payload extents, traversal depth, cycles/shared children, unreachable node gaps and duplicate path/locale identities. Distinct locales may share a path. Unsafe name components are rejected, and no path extraction occurs. For standalone bundles every declared tree node must be reachable; embedded arrays have no bundle header and only the reachable contiguous prefix is established. The latter's backing reads are bounded by the containing PE section and an explicit node cap.

Six targeted tests pass using synthetic format-v3 fixtures. They include locale variants, malformed headers, cycles/bounds/orphans, unsafe names, payload/flag failures and duplicate locale identities. The actual positive inspection separately validates all twenty selected inputs. This work changes no native build inputs, so the preceding 39/39 Release and Debug suites remain evidence for the unchanged implementation. The preceding full Python suite remains 71/71; these six new targeted checks are reported separately, without claiming a newly run full suite.

## Reproduction and integration consequence

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_qrc_index.py -v > analysis/qrc-index-tests.log 2>&1
.venv/Scripts/python.exe scripts/inspect-serato-qrc-resources.py
.venv/Scripts/python.exe scripts/export-serato-qrc-index.py
```

The exporter also requires the saved successful targeted-test log at `analysis/qrc-index-tests.log`. Reports contain input/index digests and aggregate metadata, not decoded bundles, full names tables, authentication data or payloads.

This inspection does not establish a supported external descriptor override. Combined with the [existing provider precedence](serato-resource-loading.md), it leaves no evidenced loose-file route through these selected Qt inputs. A future current-Serato integration still needs an admitted description/control/handshake path with legitimate product/account behavior, independently working ASIO, measured routing/timing and physical DVS tests. No support-value, product/account, archive or executable patch was made. The goal remains active; these findings do not claim current Serato is working with the SL3.
