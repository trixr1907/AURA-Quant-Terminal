'use strict';
const assert=require('assert');
const fs=require('fs');
const html=fs.readFileSync('Symbiose_Dashboard.html','utf8');
assert(html.includes('id="advanced-analysis-section"'),'PF-44: advanced section missing');
assert(/<details class="collapsible-advanced" id="advanced-analysis-section">/.test(html),'PF-44: manual panel must default collapsed');
assert(html.includes('Paper-Autobot optimiert den Time-Stop automatisch bei jedem Einstieg'),'PF-44: honest automation copy missing');
assert(html.includes('optimizeTimeStopForAsset'),'PF-44: automatic optimizer must remain');
console.log('PASS PF-44 manual panel demotion and automatic entry optimizer retained');
