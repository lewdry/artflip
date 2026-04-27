<script>
  import { createEventDispatcher, onMount } from 'svelte';

  export let artworkIDs = [];
  export let regenKey = 0;

  const dispatch = createEventDispatcher();

  const CELL = 31; // 30px cell + 1px gap
  const MAX_DESKTOP_COLS = 25;
  const MAX_MOBILE_COLS = 10;
  const MAX_ROWS = 15;

  let cols = MAX_DESKTOP_COLS;
  let rows = MAX_ROWS;
  let gridItems = [];

  function shuffled(arr) {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function computeGrid() {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const hPad = 32; // ~1rem padding each side
    const vReserve = 120; // header + controls + breathing room

    const isMobile = vw <= 700;
    const maxCols = isMobile ? MAX_MOBILE_COLS : MAX_DESKTOP_COLS;
    const availW = Math.min(vw - hPad, 1000 - hPad);
    const availH = vh - vReserve;

    cols = Math.max(1, Math.min(maxCols, Math.floor(availW / CELL)));
    rows = Math.max(1, Math.min(MAX_ROWS, Math.floor(availH / CELL)));
  }

  let randomOrder = [];

  function updateGridItems() {
    const count = cols * rows;
    if (randomOrder.length !== artworkIDs.length) {
      randomOrder = shuffled(artworkIDs);
    }
    gridItems = randomOrder.slice(0, count);
  }

  function generate() {
    randomOrder = shuffled(artworkIDs);
    updateGridItems();
  }

  let resizeTimer;
  function handleResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const oldCols = cols;
      const oldRows = rows;
      computeGrid();
      if (cols !== oldCols || rows !== oldRows) {
        updateGridItems();
      }
    }, 200);
  }

  let gridEl;

  let prevRegenKey = regenKey;
  $: if (regenKey !== prevRegenKey) { prevRegenKey = regenKey; generate(); }
  $: if (artworkIDs && artworkIDs.length > 0 && randomOrder.length !== artworkIDs.length) { generate(); }

  function handleGlobalInteraction(e) {
    if (activeID && gridEl && !gridEl.contains(e.target)) {
      activeID = null;
    }
  }

  onMount(() => {
    computeGrid();
    generate();
    window.addEventListener('resize', handleResize);
    window.addEventListener('touchstart', handleGlobalInteraction);
    window.addEventListener('mousedown', handleGlobalInteraction);
    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('touchstart', handleGlobalInteraction);
      window.removeEventListener('mousedown', handleGlobalInteraction);
      clearTimeout(resizeTimer);
    };
  });

  // ── Touch interaction ─────────────────────────────────────────
  // Only one cell is ever scaled at a time — whichever is under the finger.
  // A tap (no movement) navigates. Mouse clicks navigate immediately.

  let activeID = null;
  let touchMoved = false;
  let lastTouchEndTime = 0;

  function getIDAtPoint(x, y) {
    const el = document.elementFromPoint(x, y);
    const cell = el?.closest('[data-id]');
    return cell instanceof HTMLElement ? cell.dataset.id ?? null : null;
  }

  function handleTouchStart(e) {
    touchMoved = false;
    // Don't set activeID yet — wait to see if this is a swipe or a tap
  }

  function handleTouchMove(e) {
    touchMoved = true;
    const id = getIDAtPoint(e.touches[0].clientX, e.touches[0].clientY);
    if (id !== activeID) activeID = id;
  }

  function handleTouchEnd(e) {
    lastTouchEndTime = Date.now();
    if (touchMoved) {
      // Swipe ended — nothing stays scaled
      activeID = null;
      if (e.cancelable) e.preventDefault();
    } else {
      // Discrete tap
      const t = e.changedTouches[0];
      const id = getIDAtPoint(t.clientX, t.clientY);
      if (id && id === activeID) {
        // Second tap on the already-scaled cell → navigate
        dispatch('select', id);
        activeID = null;
        if (e.cancelable) e.preventDefault();
      } else {
        // First tap → scale this cell, clear any previous one
        activeID = id;
        if (e.cancelable) e.preventDefault();
      }
    }
  }

  // Mouse: navigate on click (ignore synthetic clicks from touch)
  function handleCellClick(id) {
    if (Date.now() - lastTouchEndTime < 600) return;
    dispatch('select', id);
  }
</script>

<div class="microfiche-wrap" role="presentation">
  <div
    class="microfiche-grid"
    style="grid-template-columns: repeat({cols}, 30px)"
    bind:this={gridEl}
    on:touchstart={handleTouchStart}
    on:touchmove|preventDefault={handleTouchMove}
    on:touchend={handleTouchEnd}
  >
    {#each gridItems as id (id)}
      <button
        class="cell"
        class:active={id === activeID}
        data-id={id}
        on:click={() => handleCellClick(id)}
        aria-label="View artwork {id}"
      >
        <img src="thumbs/{id}.webp" alt="" loading="lazy" on:error={e => { if (e.currentTarget instanceof HTMLElement) e.currentTarget.style.visibility = 'hidden'; }} />
      </button>
    {/each}
  </div>
  <div class="controls">
    <button class="regen-btn" on:click={() => dispatch('home')}>Home</button>
  </div>
</div>

<style>
  .microfiche-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0.5rem 0 1rem;
  }

  .microfiche-grid {
    display: grid;
    gap: 1px;
    overflow: visible;
  }

  .cell {
    width: 30px;
    height: 30px;
    padding: 0;
    border: none;
    background: #ccc;
    cursor: pointer;
    position: relative;
    z-index: 0;
    /* no overflow:hidden here — lets the scaled image bleed outside the cell */
  }

  .cell.active {
    z-index: 10;
  }

  .cell img {
    width: 30px;
    height: 30px;
    object-fit: cover;
    object-position: center;
    display: block;
    transition: transform 0.15s ease;
    position: relative;
    pointer-events: none;
    image-rendering: crisp-edges;
    image-rendering: pixelated; /* Chromium/Safari: nearest-neighbour, no smoothing */
  }

  .cell.active img {
    transform: scale(2.0);
  }

  @media (hover: hover) {
    .cell:hover {
      z-index: 10;
    }
    
    .cell:hover img {
      transform: scale(2.0);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .cell img {
      transition: none;
    }
  }

  .controls {
    margin-top: 1rem;
  }

  .regen-btn {
    background: #131C1D;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    font-family: inherit;
  }

  .regen-btn:hover {
    background: #333;
    transform: scale(1.04);
    box-shadow: 0 3px 8px rgba(0, 0, 0, 0.15);
  }

  .regen-btn:focus-visible {
    outline: 3px solid #4a90e2;
    outline-offset: 2px;
  }
</style>
