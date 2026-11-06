# Installed startup: ordinary-user activation and profile options

The install-once investigation narrows two decisions. The existing audio broker already runs without elevation, so an elevated Windows service is not established as necessary. The checked native-device schema exposes `connect_on_finish_install`, but no declared top-level startup switch among the four names tested. Neither finding implements normal Serato startup.

## The broker does not need the recurring administrator prompt

The ordinary-user broker helper starts the controller through a normal child process. `src/windows/broker_pipe.cpp` rejects an elevated owner when creating its endpoint, and its admission check requires both peers to be non-elevated with matching SID, integrity, logon authentication identity and Windows session. The controller creates that listener before acquisition. [Controller contract](broker-controller.md) · [Current helper](../scripts/serato-session-broker.py)

This is supported by earlier direct token observations for a real parent, control probe and worker. That historical component passed normal-token control/release; its wrapper failure and older worker identity remain preserved. It is not a new physical test or evidence that today's installed-use lifecycle exists. [Historical token evidence](evidence/attended-controls-components-20261031.json)

The preceding installed-use design described an elevated session owner; that was incorrect and has been corrected. Protected package staging, machine ASIO registration and optional trace collection account for the approval prompts. Prefer extending ordinary-user on-demand activation of the existing broker. Merely moving the controller to a privileged service would conflict with the current pipe identity contract and add an unnecessary privilege boundary unless later evidence establishes a separate need.

The existing locator mode resolves an already published immutable session and live broker process; that mode does not create a controller when its locator is absent. The new [lazy activation entry](asio-activation-entry.md) can now start an ordinary-user owner on ASIO initialization, but has only been exercised with simulated transport in an unregistered host. It has not been installed or tested through normal Serato startup. The separate private-worker path can construct its own worker, but the current unmeasured diagnostic mode explicitly requires the retained broker. Do not silently switch to that other backend or relabel its timing to obtain automatic startup. The missing installed-use mechanism is authenticated activation/publication and application-lifetime cleanup, not proof that the transport requires administrator rights.

## A schema-only startup flag was not found

The new [read-only inspector](../scripts/inspect-serato-installed-profile-options.py) pins the original 5.0.0.1278 executable, archive and schema. It inspects the inherited native-device declarations separately from the nested driver type. [Metadata-only result](evidence/installed-profile-options-20261106.json)

- The native-device hierarchy has 107 element declarations / 106 unique names and two attributes.
- Its only declaration containing `connect` is `connect_on_finish_install`.
- The exact names `connect_on_start`, `connect_on_launch`, `connect_on_arrival` and `auto_connect` are not declared at that level.
- The nested driver type declares audio, deck setup, driver detection and installer fields, with no attributes.

This is a bounded declaration inventory, not proof that every possible XML-only solution is absent. Nested descendants, other device kinds and executable parser extensions are not exhausted. It gives no basis for inventing a startup field or changing account/entitlement state. The installed-driver branch and real primary-selection handoff remain the next code boundaries to trace. [Existing branch evidence](serato-installed-startup-boundary.md)

The original schema includes an external XHTML DOCTYPE. The inspector removes only that exact known declaration from the in-memory parsing copy and never loads a DTD; it refuses other/repeated document types and entity declarations. Original bytes are hash-checked before this parsing-only transformation. No schema, key material, descriptor XML or vendor binary is published. Unsupported top-level compositor/reference constructs are refused rather than silently interpreted as absent fields. Repeated names inherited across types remain counted instead of being discarded.

Eight focused tests cover inheritance, attributes, separately named nested types, repeated inherited names, unknown/cyclic bases, unsupported constructs, size/entity/root bounds and exact DOCTYPE handling. Inspection against the actual pinned archive passed. The older full candidate builder was not used: it also requires its historical native-build source manifest, which currently reports CMake source drift. No native source was restored and no historical build claim was overridden to obtain this schema inspection.

No Serato launch, device open, registration, firmware or protection change ran. The installed-use target remains incomplete; Phase and timecode vinyl should share this same audio/activation route.
