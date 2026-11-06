'use strict';
// Passive startup diagnostic. Never invoke, retain or copy a vendor callback.
(() => {
  const app = Process.getModuleByName('Serato DJ Pro.exe');
  const points = [
    ['popup', 0x137df40, '48895c2418555657'],
    ['button', 0xf25270, '4053555657415648'],
    ['message', 0x137b790, '48895c2418555657'],
    ['arrival', 0x185ee90, '48895c2408574883']
  ];
  for (const [name, rva, expected] of points) {
    const bytes = Array.from(new Uint8Array(app.base.add(rva).readByteArray(8)),
      value => value.toString(16).padStart(2, '0')).join('');
    if (bytes !== expected) throw new Error('Action observer entry differs: ' + name);
  }
  const frames = new Map(), controllers = new Map();
  let emitted = 0;
  const emit = (event, fields = {}) => {
    if (emitted >= 128) return;
    ++emitted; send({event, ordinal: emitted, ...fields});
  };
  const active = () => emitted < 128;
  const id = pointer => {
    const key = pointer.toString();
    if (!controllers.has(key) && controllers.size < 8) controllers.set(key, controllers.size + 1);
    return controllers.get(key);
  };
  const arrivalPublished = thread => emit('genuine_sl3_arrival_published', {thread});
  let installed = false;
  const activate = sharedArrival => {
  if (installed) throw new Error('Action observer already active');
  installed = true;
  Interceptor.attach(app.base.add(points[0][1]), {
    onEnter(args) {
      if (!active()) return;
      this.frame = {controller: args[0], thread: this.threadId, callbacks: 0};
      const stack = frames.get(this.threadId) || [];
      stack.push(this.frame); frames.set(this.threadId, stack);
    },
    onLeave() {
      if (!this.frame) return;
      const stack = frames.get(this.threadId);
      if (!stack || stack.pop() !== this.frame) {
        frames.delete(this.threadId); emit('action_observer_fault', {stage: 'popup_stack'}); return;
      }
      if (!stack.length) frames.delete(this.threadId);
      if (this.frame.callbacks) emit('driver_popup_returned', {
        controller: id(this.frame.controller), thread: this.threadId, callbacks: this.frame.callbacks
      });
    }
  });
  Interceptor.attach(app.base.add(points[1][1]), {
    onEnter(args) {
      if (!active()) return;
      const stack = frames.get(this.threadId), frame = stack && stack[stack.length - 1];
      if (!frame) return;
      try {
        const callback = args[2];
        if (!callback.readPointer().equals(app.base.add(0x2f2bdb8))) return;
        if (!callback.readPointer().add(16).readPointer().equals(app.base.add(0x1380170))) return;
        if (!callback.add(Process.pointerSize).readPointer().equals(frame.controller)) return;
        const controller = id(frame.controller);
        if (controller === undefined) return;
        ++frame.callbacks;
        emit('driver_action_receiver_observed', {controller, thread: this.threadId,
          callbackSlot: 16, captureOffset: 8, receiverMatchesPopup: true});
      } catch (_) { emit('action_observer_fault', {stage: 'callback_read'}); }
    }
  });
  Interceptor.attach(app.base.add(points[2][1]), {
    onEnter(args) {
      if (!active()) return;
      this.controller = args[0];
      try { this.message = args[1].add(12).readU32(); }
      catch (_) { this.controller = null; }
    },
    onLeave() {
      if (!active() || !this.controller) return;
      const controller = controllers.get(this.controller.toString());
      if (controller !== undefined) emit('driver_controller_message_returned', {
        controller, thread: this.threadId, message: this.message
      });
    }
  });
  if (!sharedArrival) Interceptor.attach(app.base.add(points[3][1]), {
    onEnter(args) {
      if (!active() || args[1].toUInt32() !== 0x2d4) return;
      const packed = args[2];
      const vid = parseInt(packed.toString().slice(0, -8) || '0', 16) & 0xffff;
      const pid = packed.toUInt32() >>> 16, rev = packed.toUInt32() & 0xffff;
      if (vid === 0x1cc5 && pid === 1 && rev === 0)
        arrivalPublished(this.threadId);
    }
  });
  emit('action_observer_ready', {guardedEntries: points.length, invokesCallbacks: false,
    readsAudio: false, maximumEvents: 128});
  };
  if (globalThis.SL3_ACTION_OBSERVER_MODE === 'shared') {
    if (globalThis.SL3_ACTION_OBSERVER) throw new Error('Action observer already prepared');
    globalThis.SL3_ACTION_OBSERVER = Object.freeze({version: 1, activate: () => activate(true), arrivalPublished});
  } else {
    if (globalThis.SL3_ACTION_OBSERVER_MODE !== undefined) throw new Error('Unknown action observer mode');
    activate(false);
  }
})();
