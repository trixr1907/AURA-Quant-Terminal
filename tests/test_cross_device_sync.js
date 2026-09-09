'use strict';
/**
 * test_cross_device_sync.js — Tests für geräteübergreifende Synchronisierung & Revision-Handling
 */

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

// Test runner
let passed = 0, failed = 0;
async function test(name, fn) {
  try {
    await fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (e) {
    console.error(`  FAIL  ${name}`);
    console.error(`        ${e.message}`);
    failed++;
  }
}

function createSyncContext(sharedStore = {}) {
  const store = sharedStore;
  const localStorageMock = {
    getItem(k) { return store[k] !== undefined ? store[k] : null; },
    setItem(k, v) { store[k] = String(v); },
    removeItem(k) { delete store[k]; }
  };
  const elements = {};
  const makeElement = () => ({
    textContent: '',
    className: '',
    innerHTML: '',
    title: '',
    style: {},
    addEventListener: () => {},
    setAttribute: () => {},
    getAttribute: () => null,
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    querySelectorAll: () => []
  });

  const documentMock = {
    getElementById(id) {
      if (!elements[id]) {
        elements[id] = makeElement();
      }
      return elements[id];
    },
    querySelectorAll: () => [],
    addEventListener: () => {},
    body: makeElement()
  };

  let fetchHandler = async (url, opts) => ({
    ok: true,
    status: 200,
    json: async () => ({ ok: true, data: { _rev: 1 } })
  });

  const fetchCalls = [];
  const customFetch = async (url, opts) => {
    fetchCalls.push({ url, opts });
    return fetchHandler(url, opts);
  };

  const ctx = {
    console,
    localStorage: localStorageMock,
    document: documentMock,
    window: {
      addEventListener: () => {},
      requestAnimationFrame: (cb) => { cb(); return 1; }
    },
    $: (id) => documentMock.getElementById(id),
    fetch: customFetch,
    setInterval: () => {},
    setTimeout: (cb) => { cb(); return 1; },
    requestAnimationFrame: (cb) => { cb(); return 1; },
    Autobot: {
      loadFromObject: (obj) => { ctx.autobotLoadedObj = obj; },
      render: () => { ctx.autobotRendered = true; }
    }
  };

  vm.createContext(ctx);

  // Extract script block
  const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
  assert(scriptMatch, 'Script block not found in HTML');
  vm.runInContext(scriptMatch[1] + '; this.SyncEngine = SyncEngine; this.loadTrades = loadTrades; this.loadTradeHistory = loadTradeHistory; this.saveTrades = saveTrades; this.saveTradeHistory = saveTradeHistory;', ctx);

  return {
    ctx,
    store,
    elements,
    fetchCalls,
    setFetchHandler: (fn) => { fetchHandler = fn; }
  };
}

async function runAll() {
  console.log('[Cross-Device Sync Engine Tests]');

  await test('SyncEngine.pull: Queue overflow remains offline and not synchronizing', async () => {
    const { ctx, store, elements, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.queueOverflow = true;
    ctx.SyncEngine.pending = [{ blocked: false, mutations: [], attempts: 0 }];
    ctx.SyncEngine.bootstrapped = true;
    setFetchHandler(async () => ({ ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 2 } }) }));
    await ctx.SyncEngine.pull();
    assert.strictEqual(ctx.SyncEngine.status, 'offline');
    assert.strictEqual(elements['st-sync-t'].textContent, 'nicht synchronisiert');
  });

  await test('SyncEngine.pull: Permanently blocked pending mutation remains offline', async () => {
    const { ctx, elements, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.bootstrapped = true;
    ctx.SyncEngine.pending = [{ blocked: true, mutations: [], attempts: 3 }];
    setFetchHandler(async () => ({ ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 2 } }) }));
    await ctx.SyncEngine.pull();
    assert.strictEqual(ctx.SyncEngine.status, 'offline');
    assert.strictEqual(elements['st-sync-t'].textContent, 'nicht synchronisiert');
  });

  await test('SyncEngine.pull: Sendable pending mutation reports synchronizing', async () => {
    const { ctx, store, elements, setFetchHandler } = createSyncContext();
    store['aura-quant-terminal-active-trades-v1'] = JSON.stringify([{ id: 'trade1', coin: 'BTCUSDT' }]);
    ctx.SyncEngine.pending = [{ blocked: false, mutations: [{ key: 'aura-quant-terminal-active-trades-v1', op: 'upsert', id: 'pending', value: { id: 'pending' } }] }];
    ctx.SyncEngine.bootstrapped = true;

    let renderCalled = false;
    ctx.renderLiveTrades = () => { renderCalled = true; };
    ctx.SyncEngine.bootstrapped = true;
    setFetchHandler(async (url) => {
      if (url === '/api/state') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ok: true,
            data: {
              _rev: 5,
              'aura-quant-terminal-active-trades-v1': []
            }
          })
        };
      }
    });

    await ctx.SyncEngine.pull();
    assert.strictEqual(store['aura-quant-terminal-active-trades-v1'], JSON.stringify([{ id: 'trade1', coin: 'BTCUSDT' }]));
    assert.strictEqual(renderCalled, false);
    assert.strictEqual(ctx.SyncEngine.status, 'bootstrap');
    assert.strictEqual(elements['st-sync-t'].textContent, 'synchronisiere');
  });

  await test('SyncEngine.bootstrapIfNeeded: Bootstraps local non-empty trades if remote key is undefined', async () => {
    const { ctx, store, fetchCalls, setFetchHandler } = createSyncContext();
    store['aura-quant-terminal-active-trades-v1'] = JSON.stringify([{ id: 'bootstrap_trade' }]);

    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        const body = JSON.parse(opts.body);
        return {
          ok: true,
          status: 200,
          json: async () => ({ ok: true, rev: 2, key: body.key, state: { _rev: 2 } })
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          data: { _rev: 1 } // remote keys undefined
        })
      };
    });

    await ctx.SyncEngine.pull();
    const postCall = fetchCalls.find(c => c.opts && c.opts.method === 'POST' && c.opts.body.includes('bootstrap_trade'));
    assert.ok(postCall, 'Expected POST bootstrap call for active trades');
  });

  await test('SyncEngine.bootstrapIfNeeded: requeues every legacy value after a 409 with fresh revision', async () => {
    const { ctx, store, fetchCalls, setFetchHandler } = createSyncContext();
    store['aura-quant-terminal-active-trades-v1'] = JSON.stringify([{ id: 'legacy_trade' }]);
    ctx.SyncEngine.bootstrapped = false;
    let posts = 0;
    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        posts++;
        const body = JSON.parse(opts.body);
        if (posts === 1) return { ok: false, status: 409, json: async () => ({ code: 'ERR_STATE_CONFLICT', rev: 7, state: { _rev: 7 } }) };
        return { ok: true, status: 200, json: async () => ({ ok: true, rev: 8, key: body.key, state: { _rev: 8, [body.key]: body.value } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 6 } }) };
    });
    await ctx.SyncEngine.pull();
    assert.strictEqual(posts, 2);
    assert.strictEqual(fetchCalls.filter(c => c.opts && c.opts.method === 'POST')[1].opts.body.includes('legacy_trade'), true);
    assert.strictEqual(ctx.SyncEngine.rev, 8);
    assert.strictEqual(ctx.SyncEngine.pending.length, 0);
  });

  await test('SyncEngine.bootstrapIfNeeded: queues autobot legacy value instead of losing it on 409', async () => {
    const { ctx, store, setFetchHandler } = createSyncContext();
    store['aura-autobot-state-v2'] = JSON.stringify({ enabled: true });
    let posts = 0;
    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        posts++;
        const body = JSON.parse(opts.body);
        if (posts === 1) return { ok: false, status: 409, json: async () => ({ code: 'ERR_STATE_CONFLICT', rev: 3, state: { _rev: 3 } }) };
        return { ok: true, status: 200, json: async () => ({ ok: true, rev: 4, key: body.key, state: { _rev: 4, [body.key]: body.value } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 2 } }) };
    });
    await ctx.SyncEngine.pull();
    assert.strictEqual(posts, 2);
    assert.strictEqual(ctx.SyncEngine.rev, 4);
    assert.strictEqual(store['aura-autobot-state-v2'], JSON.stringify({ enabled: true }));
  });
  await test('SyncEngine.pushDirect: Handles 409 conflict by refreshing rev and pulling latest state', async () => {
    const { ctx, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.rev = 1;
    ctx.SyncEngine.bootstrapped = true;

    let pullCalled = false;
    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        return {
          ok: false,
          status: 409,
          json: async () => ({
            code: 'ERR_STATE_CONFLICT',
            rev: 3,
            state: { _rev: 3, 'aura-autobot-state-v2': { enabled: true } }
          })
        };
      }
      if (url === '/api/state' && (!opts || opts.method === 'GET')) {
        pullCalled = true;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ok: true,
            data: { _rev: 3, 'aura-autobot-state-v2': { enabled: true } }
          })
        };
      }
    });

    const success = await ctx.SyncEngine.pushDirect('aura-autobot-state-v2', { enabled: false }, 1);
    assert.strictEqual(success, false);
    assert.strictEqual(ctx.SyncEngine.status, 'conflict');
    assert.strictEqual(ctx.SyncEngine.rev, 3);
    assert.strictEqual(pullCalled, false);
  });

  await test('SyncEngine queue: sends mutation batches sequentially with updated revisions', async () => {
    const { ctx, fetchCalls, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.bootstrapped = true;
    const requests = [];
    setFetchHandler(async (url, opts) => {
      if (opts.method === 'POST') {
        requests.push(JSON.parse(opts.body));
        await new Promise(resolve => setTimeout(resolve, 5));
        const rev = requests.length;
        return { ok: true, status: 200, json: async () => ({ ok: true, rev, state: { _rev: rev } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 0 } }) };
    });
    const first = ctx.SyncEngine.enqueueMutations([{ key: 'aura-quant-terminal-active-trades-v1', op: 'upsert', id: 'q1', value: { id: 'q1' } }]);
    const second = ctx.SyncEngine.enqueueMutations([{ key: 'aura-quant-terminal-active-trades-v1', op: 'upsert', id: 'q2', value: { id: 'q2' } }]);
    await Promise.all([first, second]);
    assert.strictEqual(requests.length, 2);
    assert.strictEqual(requests[1].expected_rev, requests[0].expected_rev + 1);
    assert.strictEqual(ctx.SyncEngine.pending.length, 0);
    assert.strictEqual(ctx.SyncEngine.status, 'synced');
  });

  await test('SyncEngine queue: 409 keeps pending mutation and retries after server reconcile', async () => {
    const { ctx, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.bootstrapped = true;
    let posts = 0;
    setFetchHandler(async (url, opts) => {
      if (opts.method === 'POST') {
        posts++;
        if (posts === 1) return { ok: false, status: 409, json: async () => ({ code: 'ERR_STATE_CONFLICT', rev: 4, state: { _rev: 4, 'aura-quant-terminal-active-trades-v1': [] } }) };
        return { ok: true, status: 200, json: async () => ({ ok: true, rev: 5, state: { _rev: 5 } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 4, 'aura-quant-terminal-active-trades-v1': [] } }) };
    });
    await ctx.SyncEngine.enqueueMutations([{ key: 'aura-quant-terminal-active-trades-v1', op: 'upsert', id: 'retry', value: { id: 'retry' } }]);
    assert.strictEqual(posts, 2);
    assert.strictEqual(ctx.SyncEngine.pending.length, 0);
    assert.strictEqual(ctx.SyncEngine.rev, 5);
  });

  await test('SyncEngine pull: pending local mutation prevents remote overwrite', async () => {
    const { ctx, store, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.bootstrapped = true;
    store['aura-quant-terminal-active-trades-v1'] = JSON.stringify([{ id: 'local-pending' }]);
    ctx.SyncEngine.pending.push({ mutations: [{ key: 'aura-quant-terminal-active-trades-v1', op: 'upsert', id: 'local-pending', value: { id: 'local-pending' } }] });
    setFetchHandler(async () => ({ ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 8, 'aura-quant-terminal-active-trades-v1': [{ id: 'remote-old' }] } }) }));
    await ctx.SyncEngine.pull();
    assert.strictEqual(store['aura-quant-terminal-active-trades-v1'], JSON.stringify([{ id: 'local-pending' }]));
  });


  await test('SyncEngine.enqueueList: emits delete for an item removed after remote history pull', async () => {
    const { ctx, store, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.bootstrapped = true;
    let remote = [{ id: 'history-a' }, { id: 'history-b' }];
    const posts = [];
    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        const body = JSON.parse(opts.body);
        posts.push(body);
        remote = [{ id: 'history-a' }];
        return { ok: true, status: 200, json: async () => ({ ok: true, rev: 2, state: { _rev: 2, [body.key]: remote } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 1, 'aura-quant-terminal-history-trades-v1': remote } }) };
    });
    await ctx.SyncEngine.pull();
    ctx.saveTradeHistory([{ id: 'history-a' }]);
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(posts.some(body => body.mutations.some(m => m.op === 'delete' && m.id === 'history-b')));
    remote = [{ id: 'history-a' }];
    await ctx.SyncEngine.pull();
    assert.strictEqual(store['aura-quant-terminal-history-trades-v1'], JSON.stringify(remote));
  });

  await test('SyncEngine.enqueueList: emits delete before initial pull from previous local list', async () => {
    const { ctx, store, setFetchHandler } = createSyncContext();
    store['aura-quant-terminal-active-trades-v1'] = JSON.stringify([{ id: 'local-trade' }]);
    ctx.SyncEngine.bootstrapped = false;
    let posted;
    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        posted = JSON.parse(opts.body);
        return { ok: true, status: 200, json: async () => ({ ok: true, rev: 1, state: { _rev: 1 } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 0 } }) };
    });
    ctx.saveTrades([]);
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(posted.mutations.some(m => m.op === 'delete' && m.id === 'local-trade'));
  });

  await test('SyncEngine.saveTradeHistory: emits all local history deletes before initial pull', async () => {
    const { ctx, store, setFetchHandler } = createSyncContext();
    store['aura-quant-terminal-history-trades-v1'] = JSON.stringify([{ id: 'h1' }, { id: 'h2' }]);
    ctx.SyncEngine.bootstrapped = false;
    let posted;
    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        posted = JSON.parse(opts.body);
        return { ok: true, status: 200, json: async () => ({ ok: true, rev: 1, state: { _rev: 1 } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 0 } }) };
    });
    ctx.saveTradeHistory([]);
    await new Promise(resolve => setImmediate(resolve));
    assert.deepStrictEqual(posted.mutations.filter(m => m.op === 'delete').map(m => m.id).sort(), ['h1', 'h2']);
  });
  await test('SyncEngine.pull: keeps a pending mutation visibly unsynchronized', async () => {
    const { ctx, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.bootstrapped = true;
    ctx.SyncEngine.pending.push({ mutations: [{ key: 'aura-quant-terminal-history-trades-v1', op: 'upsert', id: 'pending', value: { id: 'pending' } }] });
    setFetchHandler(async () => ({ ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 2, 'aura-quant-terminal-history-trades-v1': [] } }) }));
    await ctx.SyncEngine.pull();
    assert.notStrictEqual(ctx.SyncEngine.status, 'synced');
  });

  await test('SyncEngine queue: permanent 409 is bounded and preserves blocked pending mutation', async () => {
    const { ctx, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.bootstrapped = true;
    let posts = 0;
    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        posts++;
        return { ok: false, status: 409, json: async () => ({ code: 'ERR_STATE_CONFLICT', rev: posts, state: { _rev: posts } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: posts } }) };
    });
    const pendingPromise = ctx.SyncEngine.enqueueMutations([{ key: 'aura-quant-terminal-history-trades-v1', op: 'upsert', id: 'blocked', value: { id: 'blocked' } }]).catch(() => false);
    await pendingPromise;
    assert.strictEqual(posts, ctx.SyncEngine.maxRetries);
    assert.strictEqual(ctx.SyncEngine.pending.length, 1);
    assert.strictEqual(ctx.SyncEngine.status, 'offline');
  });

  await test('SyncEngine bootstrap: applies legacy 409 state while pull is already active', async () => {
    const { ctx, store, setFetchHandler } = createSyncContext();
    store['aura-autobot-state-v2'] = JSON.stringify({ enabled: false });
    let postCount = 0;
    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        postCount++;
        return { ok: false, status: 409, json: async () => ({ code: 'ERR_STATE_CONFLICT', rev: 4, state: { _rev: 4, 'aura-autobot-state-v2': { enabled: true } } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 3 } }) };
    });
    await ctx.SyncEngine.pull();
    assert.strictEqual(postCount, 3);
    assert.strictEqual(ctx.SyncEngine.status, 'offline');
    assert.strictEqual(ctx.SyncEngine.rev, 4);
    assert.strictEqual(ctx.SyncEngine.pending.length, 1);
    assert.strictEqual(store['aura-autobot-state-v2'], JSON.stringify({ enabled: true }));
  });

  await test('SyncEngine UI: Reflects connected/synced/offline in status indicator', async () => {
    const { ctx, elements } = createSyncContext();
    ctx.SyncEngine.setStatus('synced');
    assert.strictEqual(elements['st-sync'].className, 'dot ok');
    assert.strictEqual(elements['st-sync-t'].textContent, 'synchronisiert');

    ctx.SyncEngine.setStatus('conflict');
    assert.strictEqual(elements['st-sync'].className, 'dot mid');
    assert.strictEqual(elements['st-sync-t'].textContent, 'Konflikt');

    ctx.SyncEngine.setStatus('offline');
    assert.strictEqual(elements['st-sync'].className, 'dot off');
    assert.strictEqual(elements['st-sync-t'].textContent, 'offline');
  });

  await test('durable queue: offline delete survives browser reload and remote pull', async () => {
    const shared = {};
    const first = createSyncContext(shared);
    first.store['aura-quant-terminal-active-trades-v1'] = JSON.stringify([{ id: 'offline-delete' }]);
    first.ctx.SyncEngine.bootstrapped = true;
    first.setFetchHandler(async (_url, opts) => {
      if (opts && opts.method === 'POST') throw new Error('offline');
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 1, 'aura-quant-terminal-active-trades-v1': [{ id: 'offline-delete' }] } }) };
    });
    first.ctx.saveTrades([]);
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(shared['aura-sync-pending-v1'], 'delete must be persisted before reload');
    assert.ok(JSON.parse(shared['aura-sync-pending-v1']).some(item => item.mutations.some(m => m.op === 'delete' && m.id === 'offline-delete')));

    const second = createSyncContext(shared);
    second.ctx.SyncEngine.restoreQueue();
    assert.ok(second.ctx.SyncEngine.pending.length >= 1);
    second.setFetchHandler(async (_url, opts) => {
      if (opts && opts.method === 'POST') return { ok: true, status: 200, json: async () => ({ ok: true, rev: 2, state: { _rev: 2, 'aura-quant-terminal-active-trades-v1': [] } }) };
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 1, 'aura-quant-terminal-active-trades-v1': [{ id: 'offline-delete' }] } }) };
    });
    await second.ctx.SyncEngine.init();
    assert.strictEqual(second.store['aura-quant-terminal-active-trades-v1'], '[]', 'pending delete must not resurrect on reload');
    assert.ok(!second.store['aura-sync-pending-v1'], 'queue clears only after ACK');
  });

  await test('durable queue: offline upsert survives reload and ACK', async () => {
    const shared = { 'aura-quant-terminal-active-trades-v1': '[]' };
    const first = createSyncContext(shared);
    first.ctx.SyncEngine.bootstrapped = true;
    first.setFetchHandler(async (_url, opts) => {
      if (opts && opts.method === 'POST') throw new Error('offline');
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 1, 'aura-quant-terminal-active-trades-v1': [] } }) };
    });
    await first.ctx.SyncEngine.enqueueMutations([{ key: 'aura-quant-terminal-active-trades-v1', op: 'upsert', id: 'offline-upsert', value: { id: 'offline-upsert' } }]).catch(() => false);
    assert.ok(shared['aura-sync-pending-v1']);
    const second = createSyncContext(shared);
    second.ctx.SyncEngine.restoreQueue();
    assert.ok(second.ctx.SyncEngine.pending.some(item => item.mutations.some(m => m.id === 'offline-upsert')));
    second.setFetchHandler(async (_url, opts) => opts && opts.method === 'POST'
      ? { ok: true, status: 200, json: async () => ({ ok: true, rev: 2, state: { _rev: 2 } }) }
      : { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 1, 'aura-quant-terminal-active-trades-v1': [] } }) });
    await second.ctx.SyncEngine.init();
    assert.ok(!shared['aura-sync-pending-v1']);
  });

  await test('durable queue: close batch remains atomic across reload', async () => {
    const shared = {};
    const first = createSyncContext(shared);
    first.ctx.SyncEngine.bootstrapped = true;
    first.setFetchHandler(async () => { throw new Error('offline'); });
    const batch = [
      { key: 'aura-quant-terminal-active-trades-v1', op: 'delete', id: 'close-active' },
      { key: 'aura-quant-terminal-history-trades-v1', op: 'upsert', id: 'close-history', value: { id: 'close-history' } }
    ];
    await first.ctx.SyncEngine.enqueueMutations(batch).catch(() => false);
    const second = createSyncContext(shared);
    second.ctx.SyncEngine.restoreQueue();
    assert.ok(second.ctx.SyncEngine.pending.length >= 1);
    second.setFetchHandler(async (_url, opts) => opts && opts.method === 'POST'
      ? { ok: true, status: 200, json: async () => ({ ok: true, rev: 1, state: { _rev: 1 } }) }
      : { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 0 } }) });
    const restored = second.ctx.SyncEngine.pending.find(item => item.mutations);
    assert.deepStrictEqual(JSON.parse(JSON.stringify(restored.mutations)), batch);
  });

  await test('durable queue: corrupt JSON is preserved byte-for-byte and ignored without sending', async () => {
    const raw = '{broken';
    const shared = { 'aura-sync-pending-v1': raw };
    const { ctx, fetchCalls } = createSyncContext(shared);
    await ctx.SyncEngine.init();
    assert.strictEqual(shared['aura-sync-pending-v1'], raw);
    assert.strictEqual(ctx.SyncEngine.queueCorrupt, true);
    assert.strictEqual(ctx.SyncEngine.pending.length, 0);
    assert.strictEqual(fetchCalls.filter(c => c.opts && c.opts.method === 'POST').length, 0);
    assert.strictEqual(ctx.SyncEngine.status, 'offline');
  });

  await test('durable queue: permanent conflict stays persisted without busy loop', async () => {
    const shared = {};
    const { ctx, setFetchHandler } = createSyncContext(shared);
    let posts = 0;
    setFetchHandler(async (_url, opts) => {
      if (opts && opts.method === 'POST') { posts++; return { ok: false, status: 409, json: async () => ({ rev: posts, state: { _rev: posts } }) }; }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 0 } }) };
    });
    await ctx.SyncEngine.enqueueMutations([{ key: 'aura-quant-terminal-history-trades-v1', op: 'upsert', id: 'blocked-reload', value: { id: 'blocked-reload' } }]).catch(() => false);
    const before = shared['aura-sync-pending-v1'];
    assert.strictEqual(posts, ctx.SyncEngine.maxRetries);
    assert.strictEqual(before, shared['aura-sync-pending-v1']);
    assert.ok(JSON.parse(before)[0].blocked);
  });

  await test('durable queue: queue persistence failure rejects projection and preserves existing pending work', async () => {
    const shared = {
      'aura-quant-terminal-active-trades-v1': JSON.stringify([{ id: 'must-survive' }]),
      'aura-sync-pending-v1': JSON.stringify([{ kind: 'mutations', mutations: [{ key: 'aura-quant-terminal-active-trades-v1', op: 'upsert', id: 'already-pending', value: { id: 'already-pending' } }] }])
    };
    const { ctx, setFetchHandler } = createSyncContext(shared);
    const originalSetItem = ctx.localStorage.setItem;
    ctx.localStorage.setItem = (key, value) => {
      if (key === 'aura-sync-pending-v1') throw new Error('QuotaExceededError');
      originalSetItem.call(ctx.localStorage, key, value);
    };
    setFetchHandler(async () => { throw new Error('offline'); });
    ctx.SyncEngine.restoreQueue();
    ctx.saveTrades([]);
    await new Promise(resolve => setImmediate(resolve));
    assert.strictEqual(shared['aura-quant-terminal-active-trades-v1'], JSON.stringify([{ id: 'must-survive' }]));
    assert.strictEqual(ctx.SyncEngine.pending.length, 1);
    assert.strictEqual(ctx.SyncEngine.status, 'offline');
  });

  await test('durable queue: restore overflow blocks sending and preserves raw queue', async () => {
    const items = Array.from({ length: 1001 }, (_, i) => ({ kind: 'mutations', mutations: [{ key: 'aura-quant-terminal-history-trades-v1', op: 'upsert', id: `overflow-${i}`, value: { id: `overflow-${i}` } }] }));
    const raw = JSON.stringify(items);
    const shared = { 'aura-sync-pending-v1': raw };
    const { ctx, fetchCalls } = createSyncContext(shared);
    ctx.SyncEngine.restoreQueue();
    assert.strictEqual(ctx.SyncEngine.queueOverflow, true);
    assert.strictEqual(ctx.SyncEngine.pending.length, 0);
    assert.strictEqual(shared['aura-sync-pending-v1'], raw);
    await ctx.SyncEngine.init();
    assert.strictEqual(fetchCalls.filter(c => c.opts && c.opts.method === 'POST').length, 0);
    assert.strictEqual(ctx.SyncEngine.status, 'offline');
  });

  await test('SyncEngine.pull: stale GET after POST ACK cannot overwrite revision or local state', async () => {
    const { ctx, store, setFetchHandler } = createSyncContext();
    ctx.SyncEngine.bootstrapped = true;
    ctx.SyncEngine.rev = 1;
    let resolvePull;
    setFetchHandler(async (url, opts) => {
      if (opts && opts.method === 'POST') {
        return { ok: true, status: 200, json: async () => ({ ok: true, rev: 2, state: { _rev: 2, 'aura-quant-terminal-active-trades-v1': [{ id: 'confirmed' }] } }) };
      }
      return new Promise(resolve => { resolvePull = () => resolve({ ok: true, status: 200, json: async () => ({ ok: true, data: { _rev: 1, 'aura-quant-terminal-active-trades-v1': [{ id: 'stale' }] } }) }); });
    });
    const pull = ctx.SyncEngine.pull();
    await ctx.SyncEngine.pushDirect('aura-autobot-state-v2', { enabled: true }, 1);
    resolvePull();
    await pull;
    assert.strictEqual(ctx.SyncEngine.rev, 2);
    assert.strictEqual(store['aura-quant-terminal-active-trades-v1'], JSON.stringify([{ id: 'confirmed' }]));
    assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.SyncEngine.shadow['aura-quant-terminal-active-trades-v1'])), [{ id: 'confirmed' }]);
  });

  console.log(`\n============================================================`);
  console.log(`ERGEBNIS:  ${passed} PASSED  |  ${failed} FAILED  |  ${passed + failed} TOTAL`);
  console.log(`============================================================`);
  process.exit(failed > 0 ? 1 : 0);
}

runAll();
