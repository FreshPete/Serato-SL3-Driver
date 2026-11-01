# UsbDk interface declarations

`UsbDkData.h` and `UsbDkHelper.h` are unchanged Apache-2.0 interface headers from Daynix/Red Hat UsbDk release `v1.00-22`, commit `84752c30037956149d53b498005b5368616f9257`. Copyright notices are preserved; the upstream LICENSE is included. No upstream implementation, DLL or kernel binary is included in the native build.

Sources:

- https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/UsbDkData.h
- https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDkHelper/UsbDkHelper.h
- https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/LICENSE

SHA256 of the downloaded bytes:

| File | SHA256 |
| --- | --- |
| UsbDkData.h | `8f0a0f4f10d2d6fb371e48c7c9e82af890ca75601ec4e5143949a42402d8cb83` |
| UsbDkHelper.h | `09cad2056278cd9dd5d74e66ec0115569662b6643ebc28660eeab3f089a0020c` |
| LICENSE | `09e8a9bcec8067104652c168685ab0931e7868f9c8284b66f5ae6edae5f1130b` |

The diagnostic dynamically resolves only the operations it uses. Merely linking against these declarations neither loads the external helper nor installs a driver. Plan mode performs neither operation.
