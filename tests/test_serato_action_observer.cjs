'use strict';
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname, '../scripts/serato-sl3-action-observer.js'), 'utf8');
const base = 0x140000000n, points = [
  [0x137df40n, '48895c2418555657'], [0xf25270n, '4053555657415648'],
  [0x137b790n, '48895c2418555657'], [0x185ee90n, '48895c2408574883']
];
function fixture(bad = false) {
  const memory = new Map(), bytes = new Map(), hooks = new Map(), events = [];
  class Pointer {
    constructor(value) { this.value = BigInt(value); }
    add(value) { return new Pointer(this.value + BigInt(value)); }
    equals(other) { return this.value === other.value; }
    toString() { return '0x' + this.value.toString(16); }
    toUInt32() { return Number(this.value & 0xffffffffn); }
    readPointer() { assert(memory.has(this.value), 'fixture pointer must be readable'); return new Pointer(memory.get(this.value)); }
    readU32() { assert(memory.has(this.value)); return Number(memory.get(this.value)); }
    readByteArray() { assert(bytes.has(this.value)); return Uint8Array.from(Buffer.from(bytes.get(this.value), 'hex')).buffer; }
  }
  for (const [rva, signature] of points) bytes.set(base + rva, signature);
  if (bad) bytes.set(base + points[2][0], '0000000000000000');
  const context = { Process: { pointerSize: 8, getModuleByName: name => { assert.equal(name, 'Serato DJ Pro.exe'); return {base: new Pointer(base)}; } },
    Interceptor: { attach: (address, handlers) => hooks.set(address.value - base, handlers) }, send: event => events.push(event) };
  const run = () => vm.runInNewContext(source, context);
  const ptr = value => new Pointer(value);
  const enter = (rva, args, thread = 7) => { const invocation = {threadId: thread}; hooks.get(BigInt(rva)).onEnter.call(invocation, args); return invocation; };
  const leave = (rva, invocation) => hooks.get(BigInt(rva)).onLeave.call(invocation);
  const bind = (callback, controller, table = base + 0x2f2bdb8n, action = base + 0x1380170n) => {
    memory.set(callback, table); memory.set(table + 16n, action); memory.set(callback + 8n, controller);
  };
  return {memory, hooks, events, run, ptr, enter, leave, bind};
}
let cases = 0;
{
  const f = fixture(true); assert.throws(f.run, /entry differs/); assert.equal(f.hooks.size, 0); ++cases;
}
{
  const f = fixture(); f.run(); assert.equal(f.hooks.size, 4); assert.equal(f.events[0].invokesCallbacks, false);
  f.bind(0x1000n, 0x2000n); f.enter(0xf25270, [null, null, f.ptr(0x1000n)]);
  assert.equal(f.events.length, 1, 'unrelated button construction is ignored'); ++cases;
}
{
  const f = fixture(); f.run(); const popup = f.enter(0x137df40, [f.ptr(0x2000n)]);
  f.bind(0x1000n, 0x2000n); f.enter(0xf25270, [null, null, f.ptr(0x1000n)]); f.leave(0x137df40, popup);
  assert.deepEqual(f.events.map(e => e.event), ['action_observer_ready', 'driver_action_receiver_observed', 'driver_popup_returned']);
  assert.equal(f.events[1].controller, f.events[2].controller);
  f.memory.set(0x300cn, 0x4fn); const message = f.enter(0x137b790, [f.ptr(0x2000n), f.ptr(0x3000n)]);
  f.leave(0x137b790, message); assert.equal(f.events.at(-1).message, 0x4f);
  const unknown = f.enter(0x137b790, [f.ptr(0x4000n), f.ptr(0x3000n)]); const count = f.events.length;
  f.leave(0x137b790, unknown); assert.equal(f.events.length, count);
  assert(!JSON.stringify(f.events).includes('0x2000'), 'controller addresses stay private'); ++cases;
}
for (const mode of ['wrong-capture', 'wrong-table', 'wrong-method', 'other-thread']) {
  const f = fixture(); f.run(); const popup = f.enter(0x137df40, [f.ptr(0x2000n)]);
  f.bind(0x1000n, mode === 'wrong-capture' ? 0x5000n : 0x2000n,
    mode === 'wrong-table' ? 0x6000n : base + 0x2f2bdb8n,
    mode === 'wrong-method' ? 0x7000n : base + 0x1380170n);
  f.enter(0xf25270, [null, null, f.ptr(0x1000n)], mode === 'other-thread' ? 8 : 7); f.leave(0x137df40, popup);
  assert.equal(f.events.length, 1, mode + ' must not publish a valid receiver'); ++cases;
}
{
  const f = fixture(); f.run(); const popup = f.enter(0x137df40, [f.ptr(0x2000n)]);
  f.enter(0xf25270, [null, null, f.ptr(0x9999n)]); f.leave(0x137df40, popup);
  assert.equal(f.events.at(-1).event, 'action_observer_fault'); ++cases;
}
{
  const f = fixture(); f.run();
  for (let n = 0; n < 200; ++n) f.enter(0x185ee90, [null, f.ptr(0x2d4n), f.ptr(0x1cc500010000n)]);
  assert.equal(f.events.length, 128); assert.equal(f.events[1].event, 'genuine_sl3_arrival_published'); ++cases;
}
assert(!/NativeFunction|Memory\.alloc|writePointer|Interceptor\.replace|retval\.replace/.test(source));
console.log(JSON.stringify({schema: 'sl3.action-observer-boundary-tests.v1', casesPassed: cases,
  mockedFridaBoundary: true, liveObserverValidated: false, callbacksInvoked: false}));
