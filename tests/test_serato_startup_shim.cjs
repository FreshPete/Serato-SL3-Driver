// Behavioral mock of the Frida boundary. No process attach, DLL load or device.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../scripts/serato-sl3-startup-shim.js'), 'utf8');
const actionSource = fs.readFileSync(path.join(__dirname, '../scripts/serato-sl3-action-observer.js'), 'utf8');
function setup({badEntry = false, observeAction = false, badActionEntry = false, missingAction = false} = {}) {
  const appBase = 0x140000000n, dllBase = 0x180000000n;
  const entries = new Map([[0x185ee90n, '48895c2408574883'], [0x185ec00n, '48895c2408574883'], [0x5b0cb0n, '48895c2420574883']]);
  if (observeAction) for (const [rva, bytes] of [[0x137df40n,'48895c2418555657'],[0xf25270n,'4053555657415648'],[0x137b790n,'48895c2418555657']]) entries.set(rva,bytes);
  const memory = new Map(), hooks = new Map(), events = [], writes = [];
  const state = {now: 10000, observer: null};
  class Pointer {
    constructor(value) { this.value = BigInt(value); }
    add(value) { return new Pointer(this.value + BigInt(value)); }
    sub(other) { return new Pointer(this.value - other.value); }
    toUInt32() { return Number(this.value & 0xffffffffn); }
    toInt32() { return this.toUInt32() | 0; }
    toString() { return '0x' + this.value.toString(16); }
    isNull() { return this.value === 0n; }
    equals(other) { return this.value === other.value; }
    readU16() { return Number(memory.get(this.value) || 0); }
    readU32() { return this.readU16(); }
    writeU16(value) { writes.push([this.value, value]); memory.set(this.value, value); }
    readPointer() { return new Pointer(memory.get(this.value) || 0); }
    readByteArray() {
      let bytes = entries.get(this.value - appBase);
      if (badEntry && this.value === appBase + 0x5b0cb0n) bytes = '0000000000000000';
      if (badActionEntry && this.value === appBase + 0x137df40n) bytes = '0000000000000000';
      assert.ok(bytes, 'Unexpected application entry inspected');
      return Uint8Array.from(Buffer.from(bytes, 'hex')).buffer;
    }
  }
  const p = value => new Pointer(value);
  const dll = {name: 'sl3_asio.dll', path: 'C:\\Program Files\\SL3 Rebuild\\test\\sl3_asio.dll',
    getExportByName(name) { assert.equal(name, 'DllGetClassObject'); return p(dllBase + 0x1000n); }};
  const context = {
    SL3_SESSION_CONFIG: {asioPath: dll.path}, Uint8Array,
    Date: {now: () => state.now}, send: event => events.push(event),
    Process: {
      pointerSize: 8,
      getModuleByName(name) { assert.equal(name, 'Serato DJ Pro.exe'); return {base: p(appBase)}; },
      attachModuleObserver(observer) { state.observer = observer; },
      findModuleByAddress(address) { return address.value >= dllBase && address.value < dllBase + 0x10000n ? dll : null; }
    },
    Interceptor: {attach(address, handlers) { assert.ok(!hooks.has(address.value), 'Duplicate hook'); hooks.set(address.value, handlers); }}
  };
  if (observeAction) context.SL3_SESSION_CONFIG.observeDownloadAction = true;
  function enter(address, args, thread = 7, caller = 0x13801ban) {
    const invocation = {threadId: thread, returnAddress: p(appBase + caller)};
    const handlers = hooks.get(address); assert.ok(handlers, 'Missing expected hook');
    if (handlers.onEnter) handlers.onEnter.call(invocation, args);
    return result => { if (handlers.onLeave) handlers.onLeave.call(invocation, p(result)); };
  }
  const api = {p, memory, hooks, events, writes, state, dll,
    load() { vm.runInNewContext(observeAction && !missingAction ? "globalThis.SL3_ACTION_OBSERVER_MODE = 'shared';\n"+actionSource+'\n'+source : source, context); },
    arrival(value = 0x1cc500010000n) { enter(appBase + 0x185ee90n, [p(0), p(0x2d4), p(value)]); },
    click(thread = 7, caller) { enter(appBase + 0x185ec00n, [p(0), p(0x4ff)], thread, caller); },
    panel(thread = 7, message = 0x4ff) { memory.set(0x200cn, message); enter(appBase + 0x5b0cb0n, [p(0x1000), p(0x2000)], thread); },
    enter, dllBase
  };
  return api;
}
let cases = 0;
function test(name, check) { check(); cases++; console.log('PASS ' + name); }
test('all entry guards precede any hook', () => {
  const s = setup({badEntry: true}); assert.throws(() => s.load(), /entry differs/); assert.equal(s.hooks.size, 0);
});
test('combined guards fail before either diagnostic installs hooks', () => {
  for (const options of [{badEntry:true},{badActionEntry:true},{missingAction:true}]) {
    const s=setup({observeAction:true,...options});assert.throws(()=>s.load());assert.equal(s.hooks.size,0);
  }
});
test('combined diagnostic shares arrival and preserves the manual click requirement', () => {
  const s=setup({observeAction:true});s.load();assert.equal(s.hooks.size,6);
  s.arrival();s.panel();assert.equal(s.writes.length,0);
  assert.equal(s.events.filter(e=>e.event==='genuine_sl3_arrival_published').length,1);
  assert.equal(s.events.filter(e=>e.event==='sl3_arrival_observed').length,1);
  s.click();s.panel();assert.equal(s.writes.length,3);
});
test('genuine arrival plus explicit click supplies only the three zero fields once', () => {
  const s = setup(); s.load(); assert.equal(s.hooks.size, 3); s.arrival(); s.click(); s.panel();
  assert.deepEqual(s.writes, [[0x1044n, 0x1cc5], [0x1042n, 1], [0x1040n, 0]]);
  s.memory.set(0x1044n, 0); s.memory.set(0x1042n, 0); s.click(); s.panel(); assert.equal(s.writes.length, 3);
});
test('unobserved, foreign and unsupported-revision devices cannot supply a panel identity', () => {
  for (const value of [null, 0x123400010000n, 0x1cc500020000n, 0x1cc500010001n]) {
    const s = setup(); s.load(); if (value !== null) s.arrival(value); s.click(); s.panel(); assert.equal(s.writes.length, 0);
  }
});
test('caller, thread, message and expired-click guards reject unrelated activity', () => {
  for (const scenario of ['caller', 'thread', 'message', 'expiry', 'clock-regression']) {
    const s = setup(); s.load(); s.arrival(); s.click(7, scenario === 'caller' ? 0x123n : undefined);
    if (scenario === 'expiry') s.state.now += 5001;
    if (scenario === 'clock-regression') s.state.now--;
    s.panel(scenario === 'thread' ? 8 : 7, scenario === 'message' ? 0x4fe : 0x4ff);
    assert.equal(s.writes.length, 0, scenario);
  }
});
test('existing VID, PID or revision is preserved and consumes that click', () => {
  for (const offset of [0x1044n, 0x1042n, 0x1040n]) {
    const s = setup(); s.load(); s.arrival(); s.click(); s.memory.set(offset, 9); s.panel();
    s.memory.set(offset, 0); s.panel(); assert.equal(s.writes.length, 0);
  }
});
test('an unsupported new SL3 revision invalidates an earlier identity and click', () => {
  const s = setup(); s.load(); s.arrival(); s.click(); s.arrival(0x1cc500010001n); s.panel();
  assert.equal(s.writes.length, 0);
});
test('an ASIO factory vtable outside the reviewed DLL is refused', () => {
  const s = setup(); s.load(); s.state.observer.onAdded(s.dll);
  s.memory.set(0x7000n, 0x3000n); s.memory.set(0x3000n, 0x4000n); s.memory.set(0x4018n, 0x140123456n);
  assert.throws(() => s.enter(s.dllBase + 0x1000n, [s.p(0), s.p(0), s.p(0x7000)])(0), /outside reviewed module/);
  assert.equal(s.hooks.size, 4);
});
test('only reviewed ASIO module is watched; failed starts do not signal ready', () => {
  const s = setup(); s.load();
  s.state.observer.onAdded({...s.dll, path: 'C:\\other\\sl3_asio.dll'}); assert.equal(s.hooks.size, 3);
  s.state.observer.onAdded(s.dll);
  const factory = 0x3000n, factoryTable = 0x4000n, device = 0x5000n, deviceTable = 0x6000n;
  s.memory.set(0x7000n, factory); s.memory.set(factory, factoryTable); s.memory.set(factoryTable + 24n, s.dllBase + 0x2000n);
  s.enter(s.dllBase + 0x1000n, [s.p(0), s.p(0), s.p(0x7000)])(0);
  s.memory.set(0x8000n, device); s.memory.set(device, deviceTable); s.memory.set(deviceTable + 56n, s.dllBase + 0x3000n);
  s.enter(s.dllBase + 0x2000n, [s.p(factory), s.p(0), s.p(0), s.p(0x8000)])(0);
  s.enter(s.dllBase + 0x3000n, [])(-997); assert.ok(!s.events.some(e => e.event === 'asio_live_start_end'));
  s.enter(s.dllBase + 0x3000n, [])(0); s.enter(s.dllBase + 0x3000n, [])(0);
  assert.equal(s.events.filter(e => e.event === 'asio_live_start_end').length, 1);
  assert.equal(s.hooks.size, 6); assert.equal(s.writes.length, 0);
});
console.log(`${cases} startup-shim behavioral cases passed; no application or hardware accessed`);
