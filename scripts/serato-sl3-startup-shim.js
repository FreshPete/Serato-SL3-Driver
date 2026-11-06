'use strict';
// Process-local interoperability only. The host pins the application/package,
// verifies the newly installed DLL before manual viewing, then unloads/detaches.
// No entitlement, authorization, USB identity or callback hooks are installed.
(() => {
  const config = globalThis.SL3_SESSION_CONFIG;
  if (!config || typeof config.asioPath !== 'string' || !/^[a-z]:[\\/]/i.test(config.asioPath))
    throw new Error('A reviewed absolute ASIO path is required');
  const app = Process.getModuleByName('Serato DJ Pro.exe');
  const points = [
    ['arrival', 0x185ee90, '48895c2408574883'],
    ['click', 0x185ec00, '48895c2408574883'],
    ['panel', 0x5b0cb0, '48895c2420574883']
  ];
  // Check every entry before changing any instruction bytes.
  for (const [name, rva, expected] of points) {
    const bytes = Array.from(new Uint8Array(app.base.add(rva).readByteArray(8)),
      value => value.toString(16).padStart(2, '0')).join('');
    if (bytes !== expected) throw new Error('Startup shim entry differs: ' + name);
  }
  if (config.observeDownloadAction !== undefined && typeof config.observeDownloadAction !== 'boolean')
    throw new Error('Action observation must be an explicit Boolean');
  const actionObserver = config.observeDownloadAction === true ? globalThis.SL3_ACTION_OBSERVER : null;
  if (config.observeDownloadAction === true && (!actionObserver || actionObserver.version !== 1))
    throw new Error('Prepared shared action observer required');
  if (actionObserver) actionObserver.activate();
  const emit = (event, fields = {}) => send({event, timeMs: Date.now(), ...fields});
  let arrival = null, click = null, supplied = false, started = false;
  Interceptor.attach(app.base.add(points[0][1]), {
    onEnter(args) {
      if (args[1].toUInt32() !== 0x2d4) return;
      const packed = args[2];
      const vid = parseInt(packed.toString().slice(0, -8) || '0', 16) & 0xffff;
      const pid = packed.toUInt32() >>> 16, rev = packed.toUInt32() & 0xffff;
      if (vid === 0x1cc5 && pid === 1) {
        arrival = rev === 0 ? {vid, pid, rev} : null;
        click = null;
        if (arrival) {
          emit('sl3_arrival_observed', arrival);
          if (actionObserver) actionObserver.arrivalPublished(this.threadId);
        }
      }
    }
  });
  Interceptor.attach(app.base.add(points[1][1]), {
    onEnter(args) {
      if (args[1].toUInt32() !== 0x4ff) return;
      click = null;
      if (!supplied && arrival && this.returnAddress.sub(app.base).toUInt32() === 0x13801ba) {
        click = {thread: this.threadId, at: Date.now()};
        emit('installer_action'); // Existing host waits on the genuine user action.
      }
    }
  });
  Interceptor.attach(app.base.add(points[2][1]), {
    onEnter(args) {
      if (supplied || args[1].add(12).readU32() !== 0x4ff || !click || click.thread !== this.threadId) return;
      const token = click; click = null; // A panel message can consume a click only once.
      const elapsed = Date.now() - token.at;
      if (elapsed < 0 || elapsed > 5000) return;
      const panel = args[0];
      // An existing identity is owned by Serato and must never be replaced.
      if (panel.add(0x44).readU16() !== 0 || panel.add(0x42).readU16() !== 0 || panel.add(0x40).readU16() !== 0) return;
      panel.add(0x44).writeU16(arrival.vid);
      panel.add(0x42).writeU16(arrival.pid);
      panel.add(0x40).writeU16(arrival.rev);
      supplied = true;
      emit('diagnostic_panel_identity_supplied', arrival);
    }
  });
  const watched = new Set();
  const normalize = path => path.replace(/\//g, '\\').toLowerCase();
  Process.attachModuleObserver({
    onAdded(module) {
      if (module.name.toLowerCase() !== 'sl3_asio.dll' || normalize(module.path) !== normalize(config.asioPath)) return;
      function method(object, index, handlers) {
        const address = object.readPointer().add(index * Process.pointerSize).readPointer();
        const key = address.toString();
        if (watched.has(key)) return;
        const owner = Process.findModuleByAddress(address);
        if (!owner || normalize(owner.path) !== normalize(config.asioPath)) throw new Error('ASIO method outside reviewed module');
        watched.add(key); Interceptor.attach(address, handlers);
      }
      Interceptor.attach(module.getExportByName('DllGetClassObject'), {
        onEnter(args) { this.output = args[2]; },
        onLeave(result) {
          if (result.toInt32() !== 0 || this.output.readPointer().isNull()) return;
          method(this.output.readPointer(), 3, {
            onEnter(args) { this.output = args[3]; },
            onLeave(created) {
              if (created.toInt32() !== 0 || this.output.readPointer().isNull()) return;
              method(this.output.readPointer(), 7, {
                onLeave(start) {
                  if (!started && start.toInt32() === 0) {
                    started = true; emit('asio_live_start_end', {result: 0});
                  }
                }
              });
            }
          });
        }
      });
    }
  });
  emit('trace_ready', {startupOnly: true, entryPoints: points.length});
})();
