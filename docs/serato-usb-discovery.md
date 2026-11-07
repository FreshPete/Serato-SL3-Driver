# Current Serato USB discovery contract

The checked Windows discovery path constructs a **USB identity record**, then the composite worker takes a matching record from a list. It does not open or claim a libusb device in this path. The historical SL3 `requires_usb=true` therefore does not, by itself, establish a requirement for a second USB streaming connection. Current SL3 admission and coexistence with UsbDk remain unverified.

Original installed/extracted DJ Pro 5.0.0.1278 SHA-256: `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. [Original-byte checks and exact instruction metadata](evidence/serato500-usb-discovery.json).

## Discovery and record contents

RTTI identifies `UsbDeviceDiscoveryWindows` at vtable `0x1431d6f58`, complete-object locator `0x1433edd18`. Slot +8 is `0x1421e4d10`; its enclosing unwind extent ends at `0x1421e57c7`.

The method calls verified import thunks for `libusb_get_device_list`, `libusb_get_device_descriptor`, `libusb_get_bus_number` and `libusb_get_device_address`. A failed descriptor read skips that device. The descriptor output starts at frame pointer +0xe0; words +8/+10/+12 supply vendor, product and revision. The generated string includes `Vid=0x`, `&Pid=0x`, `&BcdDevice=0x`, `&Instance=` and `#`, with bus and address supplying the instance components. This is not a USB serial-number read.

For a new identity it allocates 40 bytes and calls `0x140c01bc0`. Exact constructor stores put vendor/product/revision at record offsets 0/2/4 and the string at +8. The libusb list is freed with its unref argument set to 1. The constructor does not store a libusb device handle or device pointer in the record.

The application's entire direct `libusb-1.0.dll` import list comprises nine enumeration, descriptor and context functions, reproduced in the evidence. No direct open, claim or transfer import is present. This is not a search for every dynamically resolved or transitive operation elsewhere. The separate `libusbmuxd.dll` imports are not this component interface.

## Composite selection

RTTI identifies `UsbConnectionList` at `0x1431d6b50`, locator `0x1433eda20`. Its helper `0x1421e2150` takes owner, output shared pointer, vendor and product arguments. Under its lock it walks owner +8's list, comparing record vendor and product through the exact getters `0x140c01c50` and `0x140c01c40`. Revision and instance string are not compared in this lookup.

On a match it retains the shared record, calls `0x1421e2730` to unlink that record's list node and returns it. The removal helper compares record pointer identity, repairs both links and decrements the list count. On a miss the output shared pointer is empty. This is a record take, not a USB open.

The composite worker's call at `0x1421dc6cc` passes descriptor-derived vendor/product values to this helper. Its earlier [component counting branch](serato-component-profiles.md) separately includes the USB capability. Descriptor selection, support state, audio API, DVS fields and handshake remain independent requirements.

## Consequence and next investigation

The next application-side lifetime question is whether UsbDk redirection changes discovery identity or causes removal/rearrival of this component while ASIO opens. Bus/address participate in the identity, but no live result establishes such a change. The removal consumers below now narrow the required observation. Do not add a second transport opener merely to satisfy `requires_usb`.

### What the retained USB connection exposes

The saved 7 November silent-duplex trace shows two distinct USB child generations on the SL3's port after the initial Rane child. The first new child advertises a Windows UsbDk interface with VID/PID `2b23:cafe`. After release, the next generation enumerates successfully and Windows blocks the unchanged Rane kernel driver 8.2729 ms later. The Code Integrity event identifies the cross-certificate policy and exact original SYS hash. The Kernel-PnP event naming the SL3 follows 0.1405 ms after that. This places the Code 39 cause in the returning Rane stack. [Trace and event evidence](evidence/sl3-redirect-discovery-20261107.json)

The installed Serato libusb DLL's checked WinUSB enumeration path opens the parent hub and reads the 18-byte USB device descriptor through `IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX`. It caches that descriptor and separately stores the bus address from the same response. The descriptor export copies the descriptor from the libusb device record. The source of those bytes is the hub response, even when the Windows interface path uses a different VID/PID. Whether the live libusb enumeration includes the redirected child still depends on parent/port discovery and the hub response. [Installed binary checks](evidence/sl3-redirect-discovery-20261107.json) · [Upstream WinUSB enumeration](https://github.com/libusb/libusb/blob/v1.0.23/libusb/os/windows_winusb.c#L788-L924)

For the [retained Serato comparison](retained-normal-start-trial.md#observe-the-normal-launch), collect complete libusb snapshots before acquisition and again while the broker is ready, before launching Serato. A complete held snapshot with the expected VID/PID establishes that this comparison presents the physical identity to Serato's library. Compare revision, bus and address too if interpreting a later remove/re-add. The saved kernel trace and binary check do not establish either live library outcome.

## Discovery differences and consumed-record removal

The discovery consumer `0x1421c20e0` invokes the discovery object's slot +8, then feeds its successful snapshot to `0x1421e0df0`. That routine maintains a map keyed by the record's identity string, obtained through `0x1404f8f90` (string at record +8), using checked bytewise comparisons. It preserves the existing shared record for a continuing identity. Missing old records are delivered through observer slot +16 before new records through slot +8. The `UsbConnectionList` vtable binds those slots to `0x1421e1e70` and `0x1421e2490` respectively.

The removal callback first tries to unlink the record from the available list. If it succeeds, the record had not been consumed and no composite-removal entry is queued. Otherwise it adds the removed shared record to the list at +0x18 and invokes its configured notification callback. This distinction matters: the successful VID/PID take described above already removed a consumed record from the available list.

`0x1421e22a0` drains that queued list by swapping it with an empty list. The aggregate removal handler `0x1421be060` calls the drain at `0x1421be7e2`. For composites with a USB record, it compares the removed and held record's full identity strings: exact lengths and `memcmp` bytes must match. Its equal branch reaches `0x1421bdc90` at `0x1421beaeb`, passing the held USB component. That helper handles component removal and calls `0x1421c0970`; final audio teardown and application UI consequences have not been fully traced.

The verified distinction is therefore **VID/PID when taking an available component, full discovery identity when matching a removed consumed component**. A changed bus/address could enter this chain if it changes a successful observed snapshot. This is conditional static behaviour, not evidence that UsbDk causes it on this host, nor that every brief disappearance is sampled. Polling cadence and failure suppression remain incompletely recovered.

Further original-byte checks now follow the composite helper through conditional action 1, the `DeviceManager` observer callback and ordinary device-list publication. [Exact dispatch chain and remaining audio boundary](serato-usb-removal-dispatch.md). A downstream IASIO close remains unproved; identity observation alone cannot certify that consequence.

## Prepared read-only observer

`scripts/observe-sl3-usb-identity.py` is plan-only by default. It describes an opt-in observation using the actual installed, SHA-pinned Serato libusb DLL and the same descriptor/bus/address inputs. It binds only seven context/enumeration/descriptor APIs; no device-open, claim, control or transfer API is bound. Its numeric identity tuple represents those fields without claiming Serato's exact string formatting.

The observer filters stored records to SL3 VID/PID, flushes timestamped JSONL samples and entry markers, and refuses output overwrite. A failed list/descriptor read makes a snapshot incomplete; neither adjacent comparison may claim removal/addition. Context and successful list allocations have independent cleanup. `finished` means the observation loop returned; a native invocation must also reach `context_closed` and process exit, and neither establishes device release or application coexistence.

The interval and 60-second duration cap bound planned polling, not synchronous native call time. Use the supervisor below for a native invocation. A [real standalone baseline](usb-identity-baseline.md) now validates the observer's actual library/API path, context closure and process exit, while exposing slow enumeration. Default planning and nine mocked native/failure/evidence-gap checks remain separate software coverage:

```powershell
.venv/Scripts/python.exe scripts/observe-sl3-usb-identity.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_usb_identity_observer.py -v
```

The supervisor is now an optional part of `test-controls-host-traced.ps1` through `-WithUsbIdentity`. [Shared-window admission/coverage checks](controls-probe.md#optional-identity-observation-in-the-shared-trace-window) require complete before/after samples and bind them to the control process window. The held subwindow is not independently established, and even matching identities throughout sampled observations would not prove admitted current Serato/DVS or safe successive audio-object reopening.

## Process supervisor

`scripts/supervise-usb-identity.py` now launches the fixed observer command in a hidden child process, using argument vectors and no shell. Its default mode only prints a plan and creates no output directory. Explicit `--run` requires a fresh local result directory and checks the actual installed DLL hash before launch. The only child command is the observer; the CLI exposes no arbitrary child-command parameter.

The supervisor waits for the requested observation duration plus ten seconds, then requests termination if necessary and allows five seconds to confirm the direct child's exit. This bounds its waits around native observer calls; it does not guarantee that Windows will retire a process stuck in the kernel. An unconfirmed retirement remains failure. No retry, USB reset, rebind, firmware operation, self-elevation or policy change is performed. No job-wide descendant or device-recovery claim is inferred from the direct child exiting.

`supervisor.json` is created exclusively and flushed before launch, with the child PID saved as soon as process creation returns. stdout/stderr and partial JSONL remain for diagnosis. The parent independently checks clean exit, original observer hash, ordered complete observation lifecycle, finite timings, actual deltas, request fields and terminal counts before marking the observation successful. Complete snapshots with an empty SL3 list remain valid observations of absence; incomplete snapshots remain recorded as gaps. Neither is hardware readiness. An evidence-write failure still runs child cleanup; a failed termination or exit check cannot become success.

The read-only `--validate` mode rechecks sources, exact fixed command, retirement, parent/observer time window, raw JSONL hash and recomputed observation summary. It loads no vendor library. Planning and verification commands:

```powershell
.venv/Scripts/python.exe scripts/supervise-usb-identity.py
.venv/Scripts/python.exe scripts/supervise-usb-identity.py --validate tests/results/local/usb-identity-supervised-01
.venv/Scripts/python.exe -m unittest discover -s tests -p test_usb_identity_supervisor.py -v
```

The explicit standalone native command, for an owner-attended diagnostic, is:

```powershell
.venv/Scripts/python.exe scripts/supervise-usb-identity.py --run --seconds 5 --result-directory tests/results/local/usb-identity-supervised-01
```

A later [standalone real baseline](usb-identity-baseline.md) passes with four stable returned SL3 identities and normal observer retirement. It does not redirect the device. Eleven supervisor checks separately exercise harmless Python children and synthetic failures. The optional combined USB/WPP/control trace has not run; real identity continuity during ownership handoff remains unverified.

No application/resource/descriptor, account, registration, firmware or security change was made. Native sources and binaries are unchanged. No live USB/app test or UAC prompt ran; existing physical and software results remain earlier scoped evidence.

## Reproduction

Use the existing Ghidra project and `FocusedDecompile.java` with the PE unwind ranges below, saving `analysis/serato500-usb-discovery-01.json`:

```text
1421e4d10:1421e57c7
1421e2490:1421e272a
1421e1e70:1421e2143
1421e2150:1421e229c
```

Then run:

```powershell
.venv/Scripts/python.exe scripts/export-serato-usb-discovery.py
```

The exporter checks actual PE/import/RTTI/instruction/leaf bytes and identity literals, plus the completed report's image and unwind extents. Decompiler types and unreachable-block warnings are not ABI proof. Verification passed on the original local inputs; this is not a physical compatibility test.

The additional lifetime reports use the same focused script and are bound by filename, SHA and complete unwind extents in `lifetimeReports` in the evidence JSON. Those entries list every range needed to regenerate reports `serato500-usb-discovery-lifetime-02.json` and `-03.json` before rerunning the exporter.

The preceding observer checkpoint passed 89/89; [source/test/plan/log bindings](evidence/usb-identity-observer-build.json) preserve its scope. No native rebuild or physical observer result is included.

The supervisor checkpoint passes the full 100-test Python suite. [Source, harmless-process tests, plan and log bindings](evidence/usb-identity-supervisor-build.json) preserve its scope; native binaries and earlier hardware evidence remain unchanged.

The later [USB-completion proof](serato-usb-completion.md) follows a taken record into the composite shared-pointer member and acquired-count increment. Equal counts set an internal byte before a separate version predicate; none of these steps establishes physical audio readiness.
