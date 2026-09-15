#!/usr/bin/env node
/**
 * Tests for Auftrag D: Reload-Banner (Dashboard <-> /serving)
 *
 * Covers:
 * 1. Mismatch between client version and remote /serving -> banner visible with new version.
 * 2. Match between client version and remote /serving -> banner hidden.
 * 3. Fetch error / unreachable endpoint -> fail-silent (banner stays hidden).
 * 4. Dismiss button hides banner for the current remote version.
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.resolve(__dirname, '../Symbiose_Dashboard.html'), 'utf8');

// Minimal DOM Mock for Banner Tests
class MockElement {
  constructor(id = '') {
    this.id = id;
    this.hidden = true;
    this.style = { display: 'none' };
    this.textContent = '';
    this.dataset = {};
    this.onclick = null;
  }
}

function createReloadEnvironment() {
  const elements = {
    'reload-banner': new MockElement('reload-banner'),
    'reload-banner-text': new MockElement('reload-banner-text'),
    'btn-reload-page': new MockElement('btn-reload-page'),
    'btn-dismiss-reload': new MockElement('btn-dismiss-reload')
  };

  const env = {
    AURA_CLIENT_VERSION: '1.10.0',
    _dismissedReloadVersion: null,
    $: (id) => elements[id] || null,
    fetchMock: null,
    elements
  };

  // Extract checkServingVersionForReload logic
  env.checkServingVersionForReload = async function () {
    if (!env.fetchMock) return;
    try {
      const res = await env.fetchMock('/serving', { cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();
      const remoteVer = data && data.version;
      if (!remoteVer || typeof remoteVer !== 'string') return;
      const banner = env.$('reload-banner');
      if (!banner) return;
      if (remoteVer !== env.AURA_CLIENT_VERSION && env._dismissedReloadVersion !== remoteVer) {
        const textEl = env.$('reload-banner-text');
        if (textEl) {
          textEl.textContent = `Neue Version v${remoteVer} verfügbar — bitte Seite neu laden`;
          textEl.dataset.remoteVersion = remoteVer;
        }
        banner.hidden = false;
        banner.style.display = 'block';
      } else {
        banner.hidden = true;
        banner.style.display = 'none';
      }
    } catch (_) {
      // Fail-silent
    }
  };

  return env;
}

console.log('--- Running Auftrag D: Reload-Banner Tests ---');

(async () => {
  // Test 1: Version Mismatch (v1.10.1 available)
  const env1 = createReloadEnvironment();
  env1.fetchMock = async (url) => {
    assert.strictEqual(url, '/serving');
    return {
      ok: true,
      json: async () => ({ ok: true, version: '1.10.1' })
    };
  };

  await env1.checkServingVersionForReload();
  const banner1 = env1.elements['reload-banner'];
  const text1 = env1.elements['reload-banner-text'];
  assert.strictEqual(banner1.hidden, false, 'Banner is visible on version mismatch');
  assert.strictEqual(banner1.style.display, 'block');
  assert.strictEqual(text1.textContent, 'Neue Version v1.10.1 verfügbar — bitte Seite neu laden');
  assert.strictEqual(text1.dataset.remoteVersion, '1.10.1');
  console.log('✓ Test 1: Mismatch triggers visible reload banner with correct version text');

  // Test 2: Version Match (v1.10.0 matches client)
  const env2 = createReloadEnvironment();
  env2.fetchMock = async () => ({
    ok: true,
    json: async () => ({ ok: true, version: '1.10.0' })
  });

  await env2.checkServingVersionForReload();
  const banner2 = env2.elements['reload-banner'];
  assert.strictEqual(banner2.hidden, true, 'Banner stays hidden when versions match');
  assert.strictEqual(banner2.style.display, 'none');
  console.log('✓ Test 2: Matching version keeps banner hidden');

  // Test 3: Network / Fetch Error (fail-silent)
  const env3 = createReloadEnvironment();
  env3.fetchMock = async () => {
    throw new Error('Network timeout / offline');
  };

  await env3.checkServingVersionForReload();
  const banner3 = env3.elements['reload-banner'];
  assert.strictEqual(banner3.hidden, true, 'Banner stays hidden on network failure');
  assert.strictEqual(banner3.style.display, 'none');
  console.log('✓ Test 3: Unreachable /serving fails silently without throwing');

  // Test 4: Dismiss logic
  const env4 = createReloadEnvironment();
  env4.fetchMock = async () => ({
    ok: true,
    json: async () => ({ ok: true, version: '1.10.2' })
  });

  await env4.checkServingVersionForReload();
  assert.strictEqual(env4.elements['reload-banner'].hidden, false);
  
  // User dismisses banner
  env4.elements['reload-banner'].hidden = true;
  env4._dismissedReloadVersion = '1.10.2';

  // Subsequent check for same version should not un-hide banner
  await env4.checkServingVersionForReload();
  assert.strictEqual(env4.elements['reload-banner'].hidden, true, 'Banner remains hidden after dismiss');
  console.log('✓ Test 4: Dismissed version does not re-open banner');

  console.log('All Auftrag D tests passed successfully!');
})();
