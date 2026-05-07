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
    if (gridEl && !gridEl.contains(e.target)) {
      closeOverlay();
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

  let touchHoldTimer = null;

  function handleTouchStart(e) {
    touchMoved = false; // always reset so overlay tap detection works correctly
    if (expandedID) return; // overlay handles its own touches
    clearTimeout(touchHoldTimer);
    // Don't set activeID yet — wait to see if this is a swipe or a tap
  }

  function handleTouchMove(e) {
    if (expandedID) return; // overlay handles its own touches
    touchMoved = true;
    const id = getIDAtPoint(e.touches[0].clientX, e.touches[0].clientY);
    if (id !== activeID) {
      activeID = id;
      clearTimeout(touchHoldTimer);
      if (id) {
        touchHoldTimer = setTimeout(() => {
          if (activeID === id) loadFullRes(id);
        }, 500);
      }
    }
  }

  function handleTouchEnd(e) {
    clearTimeout(touchHoldTimer);
    if (expandedID) {
      if (touchMoved) {
        // Overlay opened via swipe-hold — finger lifting ends the swipe, leave overlay open
        if (e.cancelable) e.preventDefault();
        return;
      }
      // Deliberate tap while overlay open — image tap navigates, anywhere else closes
      const t = e.changedTouches[0];
      const el = document.elementFromPoint(t.clientX, t.clientY);
      if (el?.tagName === 'IMG' && el?.closest('.overlay')) {
        dispatch('select', expandedID);
      }
      closeOverlay();
      if (e.cancelable) e.preventDefault();
      return;
    }
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
        // Second tap on the already-scaled cell
        if (expandedID === id) {
          // Overlay is open → navigate
          dispatch('select', expandedID);
          closeOverlay();
        } else {
          // Overlay not yet loaded → navigate immediately as fallback
          dispatch('select', id);
          activeID = null;
        }
        if (e.cancelable) e.preventDefault();
      } else {
        // First tap → scale this cell, start loading full-res
        activeID = id;
        loadFullRes(id);
        if (e.cancelable) e.preventDefault();
      }
    }
  }

  // Mouse: scale + start loading full-res on click (ignore synthetic clicks from touch)
  function handleCellClick(id) {
    if (Date.now() - lastTouchEndTime < 600) return;
    activeID = id;
    loadFullRes(id);
  }

  // ── Full-res overlay ──────────────────────────────────────────
  let hoveredID = null;
  let expandedID = null;
  let expandedSrc = null;
  let expandedOrigin = { x: 0, y: 0 };

  function loadFullRes(id) {
    dispatch('prefetch', id); // warm metadata cache immediately
    const img = new Image();
    img.src = `images/${id}.jpg`;
    img.onload = () => {
      if (hoveredID === id || activeID === id) {
        const cellEl = gridEl?.querySelector(`[data-id="${id}"]`);
        if (cellEl && gridEl) {
          const cellRect = cellEl.getBoundingClientRect();
          const gridRect = gridEl.getBoundingClientRect();
          expandedOrigin = {
            x: cellRect.left - gridRect.left + cellRect.width / 2,
            y: cellRect.top - gridRect.top + cellRect.height / 2,
          };
        }
        expandedID = id;
        expandedSrc = `images/${id}.jpg`;
        activeID = null; // remove 2× scale from the cell once overlay is shown
      }
    };
  }

  function closeOverlay() {
    if (expandedID) dispatch('uncache', expandedID);
    expandedID = null;
    expandedSrc = null;
    activeID = null;
  }

  // ── Hover-based prefetch + full-res load ──────────────────────
  // Desktop only: if the pointer rests on a cell for >300ms, prefetch metadata
  // and start loading the full-res image in the background.
  let hoverTimer = null;

  function handleCellMouseEnter(id) {
    hoveredID = id;
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => {
      loadFullRes(id); // dispatches prefetch internally
    }, 500);
  }

  function handleCellMouseLeave() {
    hoveredID = null;
    clearTimeout(hoverTimer);
  }
</script>

<div class="grid-view-wrap" role="presentation">
  <div
    class="grid-view-grid"
    aria-hidden="true"
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
        on:mouseenter={() => handleCellMouseEnter(id)}
        on:mouseleave={handleCellMouseLeave}
      >
        <img src="thumbs/{id}.webp" alt="" loading="lazy" on:error={e => { if (e.currentTarget instanceof HTMLElement) e.currentTarget.style.visibility = 'hidden'; }} />
      </button>
    {/each}

    {#if expandedID}
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div class="overlay" style="transform-origin: {expandedOrigin.x}px {expandedOrigin.y}px" on:click={closeOverlay}>
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
        <img
          src={expandedSrc}
          alt=""
          on:click|stopPropagation={() => { dispatch('select', expandedID); closeOverlay(); }}
        />
      </div>
    {/if}
  </div>
</div>

<style>
  .grid-view-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0;
    background: white;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.07);
  }

  .grid-view-grid {
    display: grid;
    gap: 1px;
    overflow: visible;
    position: relative;
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

  @keyframes expand-from-cell {
    from {
      transform: scale(0.05);
      opacity: 0;
    }
    to {
      transform: scale(1);
      opacity: 1;
    }
  }

  .overlay {
    position: absolute;
    inset: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px; /* ~1.3 cells (31px each) from each edge */
    background: rgba(0, 0, 0, 0.6);
    cursor: pointer;
    animation: expand-from-cell 0.25s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  }

  .overlay img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    cursor: pointer;
    display: block;
  }

</style>
