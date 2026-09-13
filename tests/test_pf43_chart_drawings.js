'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

assert(html.includes('id="tool-hline"'), 'PF-43: horizontal tool missing');
assert(html.includes('id="tool-trend"'), 'PF-43: trend tool missing');
assert(html.includes('📌 Lokal gespeichert'), 'PF-43: local-only notice missing');
assert(html.includes('drawUserChartDrawings(ctx'), 'PF-43: render overlay integration missing');

const store = {};
const ctx = {
 console, JSON, Math, Date, Promise, Set, Map, Number, String, Array, Object,
 localStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>store[k]=String(v),removeItem:k=>delete store[k]},
 document:{getElementById:()=>null,querySelectorAll:()=>({forEach(){}}),addEventListener(){},createElement:()=>({}),body:{}},
 window:{addEventListener(){},requestAnimationFrame:cb=>cb()}, setTimeout:()=>1,setInterval:()=>1,clearTimeout(){},requestAnimationFrame:cb=>cb(),fetch:async()=>({ok:true,json:async()=>({})}),location:{search:''}
};
vm.createContext(ctx);
vm.runInContext(`${script}; this.App=App; this.sanitizeDrawing=sanitizeDrawing; this.saveChartDrawings=saveChartDrawings; this.loadChartDrawings=loadChartDrawings; this.drawingPointToCanvas=drawingPointToCanvas; this.findDrawingHit=findDrawingHit;`,ctx);
const trend={id:'t1',type:'trend',points:[{time:100,price:10},{time:200,price:20}]};
assert(ctx.sanitizeDrawing(trend), 'PF-43: valid trend must survive sanitation');
ctx.App.symbol='BTCUSDT'; ctx.App.drawings=[trend]; ctx.saveChartDrawings();
assert.strictEqual(ctx.loadChartDrawings()[0].points[1].price,20,'PF-43: drawing persistence failed');
const plot={xAtTime:t=>t,yAt:p=>100-p};
assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.drawingPointToCanvas(trend.points[0],plot))),{x:100,y:90});
assert(ctx.findDrawingHit(100,90,plot,[trend]),'PF-43: anchor hit testing failed');
trend.points[0]={time:120,price:12}; ctx.App.drawings=[trend]; ctx.saveChartDrawings();
assert.strictEqual(ctx.loadChartDrawings()[0].points[0].time,120,'PF-43: move/persist failed');
ctx.App.drawings=[]; ctx.saveChartDrawings(); assert.strictEqual(ctx.loadChartDrawings().length,0,'PF-43: deletion persistence failed');
console.log('PASS PF-43 drawing create/move/delete persistence and price-time projection');
