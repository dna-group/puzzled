# app.py
# Streamlit + embedded client-side Slitherlink UI with "Bookmark" button that builds a full URL
# containing the encoded puzzle state. The button will try to update the top-level URL (same-origin)
# and otherwise copy the URL to the clipboard for manual bookmarking.
#
# - Grid: 128 x 178
# - Minimal UI (no visible HUD besides the Bookmark button)
# - Top-left of puzzle aligned to top-left of canvas on start
# - Puzzle state (edges + viewport) encoded into a URL-safe base64 token in the fragment (#state=...)
#
# Usage:
#   pip install streamlit
#   streamlit run app.py

import streamlit as st
from streamlit.components.v1 import html

st.set_page_config(layout="wide")
html_code = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Slitherlink (bookmarkable)</title>
<style>
  html,body {
    height:100%;
    margin:0;
    background:#ddd;   /* page background to highlight puzzle border */
  }
  #container {
    position:relative;
    height:100vh;
    width:100vw;
    background:#ddd;
    overflow:hidden;
  }
  canvas {
    display:block;
    background:#fff;   /* puzzle background */
    touch-action:none;
  }

  /* Bookmark button */
  #bookmarkBtn {
    position: fixed;
    top: 12px;
    right: 12px;
    z-index: 9999;
    background: #222;
    color: #fff;
    border: none;
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    opacity: 0.95;
  }
  #bookmarkBtn:active { transform: translateY(1px); }
</style>
</head>
<body>
<div id="container">
  <canvas id="mainCanvas"></canvas>
</div>

<button id="bookmarkBtn" title="Copy bookmark link">🔖 Bookmark</button>

<script>
(() => {
  // CONFIG / GRID
  const COLS = 128;
  const ROWS = 178;
  const DOT_SPACING = 9;
  const DOT_RADIUS = 1.0;
  const EDGE_HIT_RADIUS = 10;
  const INITIAL_ZOOM = 3.2;
  const BORDER = DOT_SPACING * 2; // margin so edges do not clip

  const gridWidth  = (COLS - 1) * DOT_SPACING;
  const gridHeight = (ROWS - 1) * DOT_SPACING;
  const fullWidth  = gridWidth  + BORDER * 2;
  const fullHeight = gridHeight + BORDER * 2;

  // DOM
  const container = document.getElementById("container");
  const canvas = document.getElementById("mainCanvas");
  const ctx = canvas.getContext("2d", { alpha:false });
  const bookmarkBtn = document.getElementById('bookmarkBtn');

  // State
  let zoom = INITIAL_ZOOM;
  let viewport = { cx: null, cy: null, w: null, h: null }; // initialised on resize/load

  // edges: Map keyed "i1,j1|i2,j2"
  const edges = new Map();
  const degree = new Map();

  const nodeKey = (x,y) => `${x},${y}`;
  const edgeKey = (a,b) => {
    const ka = nodeKey(a.x,a.y), kb = nodeKey(b.x,b.y);
    return ka < kb ? ka + '|' + kb : kb + '|' + ka;
  };

  function addEdge(a,b){
    const k = edgeKey(a,b);
    if (edges.has(k)) return false;
    const da = degree.get(nodeKey(a.x,a.y))||0;
    const db = degree.get(nodeKey(b.x,b.y))||0;
    if (da >= 2 || db >= 2) return false;
    edges.set(k,true);
    degree.set(nodeKey(a.x,a.y), da+1);
    degree.set(nodeKey(b.x,b.y), db+1);
    scheduleSaveState(); // persist change to URL fragment (iframe-level)
    return true;
  }
  function removeEdge(a,b){
    const k = edgeKey(a,b);
    if (!edges.has(k)) return false;
    edges.delete(k);
    degree.set(nodeKey(a.x,a.y), (degree.get(nodeKey(a.x,a.y))||1)-1);
    degree.set(nodeKey(b.x,b.y), (degree.get(nodeKey(b.x,b.y))||1)-1);
    scheduleSaveState();
    return true;
  }

  function fullToScreen(x,y){
    const l = viewport.cx - viewport.w/2;
    const t = viewport.cy - viewport.h/2;
    return {
      x: (x - l) / viewport.w * canvas.width,
      y: (y - t) / viewport.h * canvas.height
    };
  }
  function screenToFull(sx, sy){
    const l = viewport.cx - viewport.w/2;
    const t = viewport.cy - viewport.h/2;
    return {
      x: l + sx / canvas.width * viewport.w,
      y: t + sy / canvas.height * viewport.h
    };
  }

  function resizeCanvas(){
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    viewport.w = canvas.width / zoom;
    viewport.h = canvas.height / zoom;
    if (viewport.cx === null) viewport.cx = viewport.w/2;
    if (viewport.cy === null) viewport.cy = viewport.h/2;
  }

  function draw(){
    ctx.fillStyle = "#fff";
    ctx.fillRect(0,0,canvas.width,canvas.height);

    // visible bounds
    const left = viewport.cx - viewport.w/2;
    const top  = viewport.cy - viewport.h/2;
    const right = left + viewport.w;
    const bottom = top + viewport.h;
    const minI = Math.max(0, Math.floor((left - BORDER) / DOT_SPACING) - 1);
    const maxI = Math.min(COLS-1, Math.ceil((right - BORDER) / DOT_SPACING) + 1);
    const minJ = Math.max(0, Math.floor((top - BORDER) / DOT_SPACING) - 1);
    const maxJ = Math.min(ROWS-1, Math.ceil((bottom - BORDER) / DOT_SPACING) + 1);

    // dots (black)
    ctx.fillStyle = "#000";
    const r = Math.max(0.6, DOT_RADIUS * zoom/2);
    for (let j = minJ; j <= maxJ; j++){
      for (let i = minI; i <= maxI; i++){
        const fx = BORDER + i * DOT_SPACING;
        const fy = BORDER + j * DOT_SPACING;
        const p = fullToScreen(fx, fy);
        if (p.x < -4 || p.x > canvas.width + 4 || p.y < -4 || p.y > canvas.height + 4) continue;
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI*2);
        ctx.fill();
      }
    }

    // edges (grey)
    ctx.strokeStyle = "#888";
    ctx.lineWidth = Math.max(3, zoom * 1.1);
    ctx.lineCap = "round";
    ctx.beginPath();
    edges.forEach((_, k) => {
      const [a,b] = k.split("|").map(s => s.split(",").map(Number));
      const p1 = fullToScreen(BORDER + a[0]*DOT_SPACING, BORDER + a[1]*DOT_SPACING);
      const p2 = fullToScreen(BORDER + b[0]*DOT_SPACING, BORDER + b[1]*DOT_SPACING);
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
    });
    ctx.stroke();
  }

  // Robust UTF-8 safe base64 URL-safe encode/decode using TextEncoder/TextDecoder
  function encodeStateToString(stateObj){
    try {
      const json = JSON.stringify(stateObj);
      const encoder = new TextEncoder();
      const bytes = encoder.encode(json);
      let binary = "";
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
      let b64 = btoa(binary);
      b64 = b64.replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
      return b64;
    } catch(e) {
      return "";
    }
  }
  function decodeStateFromString(s){
    try {
      s = s.replace(/-/g,'+').replace(/_/g,'/');
      while (s.length % 4 !== 0) s += '=';
      const binary = atob(s);
      const len = binary.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
      const decoder = new TextDecoder();
      const json = decoder.decode(bytes);
      return JSON.parse(json);
    } catch(e) {
      return null;
    }
  }

  // Read state from URL (fragment first, then query param), return object or null
  function loadStateFromURL(){
    const hash = window.location.hash || "";
    if (hash.startsWith("#state=")){
      const payload = hash.slice(7);
      return decodeStateFromString(payload);
    }
    const q = new URLSearchParams(window.location.search);
    if (q.has("state")) return decodeStateFromString(q.get("state"));
    return null;
  }

  // Apply state (edges array and optional viewport)
  function applyState(obj){
    if (!obj) return;
    edges.clear();
    degree.clear();
    if (Array.isArray(obj.edges)){
      for (const e of obj.edges){
        if (!Array.isArray(e) || e.length < 4) continue;
        const a = { x: e[0], y: e[1] }, b = { x: e[2], y: e[3] };
        const k = edgeKey(a,b);
        edges.set(k,true);
        degree.set(nodeKey(a.x,a.y), (degree.get(nodeKey(a.x,a.y))||0)+1);
        degree.set(nodeKey(b.x,b.y), (degree.get(nodeKey(b.x,b.y))||0)+1);
      }
    }
    if (obj.viewport && typeof obj.viewport === "object"){
      if (typeof obj.viewport.zoom === "number" && obj.viewport.zoom > 0) zoom = obj.viewport.zoom;
      if (typeof obj.viewport.cx === "number") viewport.cx = obj.viewport.cx;
      if (typeof obj.viewport.cy === "number") viewport.cy = obj.viewport.cy;
      viewport.w = canvas.width / zoom;
      viewport.h = canvas.height / zoom;
      viewport.cx = Math.max(viewport.w/2, Math.min(fullWidth - viewport.w/2, viewport.cx));
      viewport.cy = Math.max(viewport.h/2, Math.min(fullHeight - viewport.h/2, viewport.cy));
    }
  }

  // Save state into URL fragment (debounced) - writes into iframe's URL fragment
  let saveTimer = null;
  function scheduleSaveState(delay = 500){
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      saveTimer = null;
      saveStateToURL();
    }, delay);
  }
  function saveStateToURL(){
    const edgesArr = [];
    edges.forEach((_, k) => {
      const [a,b] = k.split("|");
      const aa = a.split(",").map(Number), bb = b.split(",").map(Number);
      edgesArr.push([aa[0], aa[1], bb[0], bb[1]]);
    });
    const stateObj = {
      edges: edgesArr,
      viewport: { cx: viewport.cx, cy: viewport.cy, zoom: zoom }
    };
    const token = encodeStateToString(stateObj);
    if (!token) return;
    const newHash = "#state=" + token;
    // this changes the iframe fragment (useful for restore within iframe)
    history.replaceState(null, "", window.location.pathname + window.location.search + newHash);
  }

  // Try to restore on load
  function tryRestoreFromURL(){
    const obj = loadStateFromURL();
    if (!obj) return false;
    applyState(obj);
    return true;
  }

  // Find nearest edge (search neighborhood)
  function findNearestEdgeToFull(fullX, fullY){
    const gx = (fullX - BORDER) / DOT_SPACING;
    const gy = (fullY - BORDER) / DOT_SPACING;
    const ix = Math.round(gx), iy = Math.round(gy);
    let best = { dist: Infinity, a: null, b: null };
    for (let dx=-2; dx<=2; dx++){
      for (let dy=-2; dy<=2; dy++){
        const nx = ix+dx, ny = iy+dy;
        if (nx >= 0 && nx+1 < COLS && ny >=0 && ny < ROWS){
          const ax = BORDER + nx*DOT_SPACING, ay = BORDER + ny*DOT_SPACING;
          const bx = BORDER + (nx+1)*DOT_SPACING, by = BORDER + ny*DOT_SPACING;
          const mx = 0.5*(ax+bx), my = 0.5*(ay+by);
          const d2 = (mx-fullX)*(mx-fullX) + (my-fullY)*(my-fullY);
          if (d2 < best.dist){ best = { dist:d2, a:{x:nx,y:ny}, b:{x:nx+1,y:ny} }; }
        }
        if (nx >= 0 && nx < COLS && ny >=0 && ny+1 < ROWS){
          const ax = BORDER + nx*DOT_SPACING, ay = BORDER + ny*DOT_SPACING;
          const bx = BORDER + nx*DOT_SPACING, by = BORDER + (ny+1)*DOT_SPACING;
          const mx = 0.5*(ax+bx), my = 0.5*(ay+by);
          const d2 = (mx-fullX)*(mx-fullX) + (my-fullY)*(my-fullY);
          if (d2 < best.dist){ best = { dist:d2, a:{x:nx,y:ny}, b:{x:nx,y:ny+1} }; }
        }
      }
    }
    return best;
  }

  // Pointer logic
  let isPointerDown = false;
  let pointerStart = null;
  let isDragging = false;
  const DRAG_THRESHOLD = 6;

  canvas.addEventListener('pointerdown', (ev) => {
    canvas.setPointerCapture(ev.pointerId);
    isPointerDown = true;
    isDragging = false;
    pointerStart = { x: ev.clientX, y: ev.clientY, cx: viewport.cx, cy: viewport.cy };
  });

  window.addEventListener('pointermove', (ev) => {
    if (!isPointerDown || !pointerStart) return;
    const dx = ev.clientX - pointerStart.x;
    const dy = ev.clientY - pointerStart.y;
    if (!isDragging && Math.hypot(dx,dy) > DRAG_THRESHOLD) isDragging = true;
    if (isDragging){
      const fx = -dx * (viewport.w / canvas.width);
      const fy = -dy * (viewport.h / canvas.height);
      viewport.cx = Math.max(viewport.w/2, Math.min(fullWidth - viewport.w/2, pointerStart.cx + fx));
      viewport.cy = Math.max(viewport.h/2, Math.min(fullHeight - viewport.h/2, pointerStart.cy + fy));
      draw();
      scheduleSaveState(300);
    }
  });

  canvas.addEventListener('pointerup', (ev) => {
    canvas.releasePointerCapture(ev.pointerId);
    if (!isPointerDown) return;
    isPointerDown = false;
    const dx = ev.clientX - pointerStart.x;
    const dy = ev.clientY - pointerStart.y;
    if (!isDragging && Math.hypot(dx,dy) <= DRAG_THRESHOLD){
      const rect = canvas.getBoundingClientRect();
      const sx = ev.clientX - rect.left;
      const sy = ev.clientY - rect.top;
      const full = screenToFull(sx, sy);
      const nearest = findNearestEdgeToFull(full.x, full.y);
      if (nearest && nearest.dist !== Infinity){
        // map world distance to approx screen pixels: d_screen ≈ sqrt(dist) * (canvas.width / viewport.w)
        const distScreen = Math.sqrt(nearest.dist) * (canvas.width / viewport.w);
        if (distScreen <= EDGE_HIT_RADIUS){
          const k = edgeKey(nearest.a, nearest.b);
          if (edges.has(k)) { removeEdge(nearest.a, nearest.b); }
          else { addEdge(nearest.a, nearest.b); }
          draw();
        }
      }
    }
    pointerStart = null;
    isDragging = false;
  });

  // Bookmark handling: builds a full URL including #state=token,
  // tries to set top-level location (same-origin), otherwise copies to clipboard.
  async function buildFullBookmarkURL(){
    const edgesArr = [];
    edges.forEach((_, k) => {
      const [a,b] = k.split("|");
      const aa = a.split(",").map(Number), bb = b.split(",").map(Number);
      edgesArr.push([aa[0], aa[1], bb[0], bb[1]]);
    });
    const stateObj = { edges: edgesArr, viewport: { cx: viewport.cx, cy: viewport.cy, zoom: zoom } };
    const token = encodeStateToString(stateObj);
    if (!token) return null;
    const fullUrl = window.location.origin + window.location.pathname + window.location.search + '#state=' + token;
    return fullUrl;
  }

  async function copyToClipboard(text){
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch(e){
      // fallback
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        return true;
      } catch(err) {
        return false;
      }
    }
  }

  bookmarkBtn.addEventListener('click', async () => {
    const url = await buildFullBookmarkURL();
    if (!url) { alert('Unable to build bookmark URL.'); return; }

    // Try to update top-level location if same-origin or not in an iframe.
    let updatedTop = false;
    try {
      if (window.top === window) {
        // not in iframe
        window.location.replace(url);
        updatedTop = true;
      } else if (window.top && window.top.location && window.top.location.origin === window.location.origin) {
        // same-origin parent -> allowed
        window.top.location.replace(url);
        updatedTop = true;
      }
    } catch (e) {
      updatedTop = false;
    }

    if (updatedTop) return; // browser address bar updated

    // fallback: copy link to clipboard and prompt user
    const ok = await copyToClipboard(url);
    if (ok) {
      alert('Bookmark link copied to clipboard. Paste it in your browser address bar and bookmark the page.');
    } else {
      window.prompt('Copy this link and bookmark it:', url);
    }
  });

  // Initialize: resize, set top-left alignment, then try to restore state and write iframe-level state
  function initialize(){
    resizeCanvas();
    viewport.w = canvas.width / zoom;
    viewport.h = canvas.height / zoom;
    viewport.cx = viewport.w/2; // left/top aligned to puzzle top-left
    viewport.cy = viewport.h/2;

    const restored = tryRestoreFromURL();
    if (!restored) {
      viewport.cx = Math.max(viewport.w/2, Math.min(fullWidth - viewport.w/2, viewport.cx));
      viewport.cy = Math.max(viewport.h/2, Math.min(fullHeight - viewport.h/2, viewport.cy));
    }
    // write iframe fragment so the iframe URL reflects current state (useful for restore within iframe)
    saveStateToURL();
    draw();
  }

  // Window resize handling
  window.addEventListener('resize', () => {
    resizeCanvas();
    viewport.w = canvas.width / zoom;
    viewport.h = canvas.height / zoom;
    viewport.cx = Math.max(viewport.w/2, Math.min(fullWidth - viewport.w/2, viewport.cx || viewport.w/2));
    viewport.cy = Math.max(viewport.h/2, Math.min(fullHeight - viewport.h/2, viewport.cy || viewport.h/2));
    draw();
  });

  // Keyboard helpers (zoom/pan) — update iframe fragment when changed
  window.addEventListener('keydown', (ev) => {
    const step = Math.max(10, 0.06 * Math.min(viewport.w, viewport.h));
    let changed = false;
    if (ev.key === 'ArrowLeft') { viewport.cx = Math.max(viewport.w/2, viewport.cx - step); changed = true; }
    if (ev.key === 'ArrowRight'){ viewport.cx = Math.min(fullWidth - viewport.w/2, viewport.cx + step); changed = true; }
    if (ev.key === 'ArrowUp')   { viewport.cy = Math.max(viewport.h/2, viewport.cy - step); changed = true; }
    if (ev.key === 'ArrowDown') { viewport.cy = Math.min(fullHeight - viewport.h/2, viewport.cy + step); changed = true; }
    if (ev.key === '+' || ev.key === '=') { zoom = Math.min(8, zoom * 1.2); viewport.w = canvas.width/zoom; viewport.h = canvas.height/zoom; changed = true; }
    if (ev.key === '-' || ev.key === '_') { zoom = Math.max(0.6, zoom / 1.2); viewport.w = canvas.width/zoom; viewport.h = canvas.height/zoom; changed = true; }
    if (changed) { draw(); scheduleSaveState(); }
  });

  // initialize and draw
  initialize();

  // Expose simple API for debugging from browser console:
  window.slither = {
    exportState: () => {
      const arr = [];
      edges.forEach((_, k) => {
        const [a,b] = k.split("|");
        const aa = a.split(",").map(Number), bb = b.split(",").map(Number);
        arr.push([aa[0], aa[1], bb[0], bb[1]]);
      });
      return { edges: arr, viewport: { cx: viewport.cx, cy: viewport.cy, zoom: zoom } };
    },
    importState: (obj) => { applyState(obj); draw(); scheduleSaveState(); }
  };

})();
</script>
</body>
</html>
"""

html(html_code, height=900)
