# Current Serato output graph routing

Serato's current output graph interprets `hw_dest` as a stereo-pair index: each configured value `h` becomes destination ports **`2*h` and `2*h+1`** on `GraphOutNode`. This is independently checked on the output path, rather than inferred from the already recovered input consumer. It establishes logical graph routing, not physical SL3 playback, final backend conversion or a usable current-device descriptor.

The original Windows x64 5.0.0.1278 PE remains SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. All addresses below are preferred image VAs. The investigation reads PE bytes and focused decompilations only; it does not execute or change Serato. [Verified output evidence](evidence/serato500-output-routing.json).

## Descriptor and mixer configuration

Parser `0x1405C7F90` reads `output_endpoints` / `mixer_out`. At `0x1405CADF0` it copies the sequential output index into a per-entry local. An explicit `hw_dest` can replace that local through the integer parser at `0x1405CAE11`. The map receives the resulting value, then the sequential index increments at `0x1405CAEEE`. The original SL3 resource declares no explicit destination overrides.

Output enum initializer `0x1405C3C10`, called by `0x14020C400` for map `0x143EBEB28`, constructs the deck names from immediate little-endian bytes and associates:

| Endpoint | Current enum key |
| --- | --- |
| Deck1Out | 3 |
| Deck2Out | 4 |
| Deck3Out | 5 |

These keys differ from the input keys 2/3/4. They are also distinct from hardware pair indices. An adapter must preserve those distinctions instead of reusing input enum numbers for output.

The previously recovered mixer setup copies the descriptor's output map into `CNativeMixer` complete-object +0x188. Configuration builder `0x142148ED0` copies its endpoint keys and pair values into a temporary map. At `0x14214AD77` it passes a configuration beginning at RBP+0xF0 into graph factory `0x1422901D0`; that map's root is at RBP+0xF8. The factory forwards the same configuration to output builder `0x14228E2A0`, which reads its map at configuration +0x08.

## Stereo destination ports and connection direction

Output builder `0x14228E2A0` locates the node named `graphOut` and checks its dynamic type against `serato::audio::model::GraphOutNode`. Its slot-effect path calculates an internal source pair position and separately doubles the map's hardware destination value:

```text
0x14228E5FE  read hw_dest from map node +0x20
0x14228E601  form 2*hw_dest
0x14228E664  connect left source to that destination port
0x14228E669  form 2*hw_dest+1
0x14228E683  connect right source to that destination port
```

The destination argument is verified through the graph connection helper `0x1414DB7F0`, rather than guessed from its decompiled signature. Its fifth argument updates connection property +0x280 and its sixth updates +0x288. Constructor `0x14143EB60` labels those properties **`FromPort`** and **`ToPort`** respectively. The two calls above pass the doubled hardware value and its successor as the sixth stack argument. They therefore select destination ports, not merely a source-channel slice or an allocation size.

The endpoint can resolve through additional source-node/slot choices; this does not mean its logical enum number is the direct source-port number. Wider graph construction and product/connection prerequisites still apply.

## Conditional historical SL3 order

The separately verified 2.5.5/2.5.6 resources declare `Deck3Out, Deck1Out, Deck2Out` with no overrides. Applying the current parser and output-graph rules yields:

| Historical endpoint | Default hardware pair | Graph output ports |
| --- | --- | --- |
| Deck3Out | 0 | 0, 1 |
| Deck1Out | 1 | 2, 3 |
| Deck2Out | 2 | 4, 5 |

This matches the pair order inferred on input, while using different output enum keys. It is a conditional descriptor-to-graph result. The current discontinued SL3 stub has not been replaced with that historical configuration, and no application file, graph state or resource was modified.

The result supplies a concrete routing requirement for the eventual connection adapter: retain the six-channel order and the auxiliary/third pair instead of compacting two decks into the first four channels. Backend sample conversion, actual ASIO channel order, physical output jacks, signal level/polarity, software through and analogue playback still need real verification. The graph-port result is not an audible-output test or a DVS result.

Reproduce with `.venv/Scripts/python.exe scripts/export-serato-output-routing-evidence.py`. The exporter checks the exact PE hash and unwind ranges, inline enum names/stores, parser attributes, mixer/configuration forwarding, doubled destination indices, and the connection property's `ToPort` assignment. It binds the previously verified historical resource evidence by hash and checks output order. No native source changed, so repeating unrelated C++ tests would add no evidence for this static result.
