<script>
  import { createEventDispatcher, onMount } from 'svelte';

  export let artworkIDs = [];

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

  function generate() {
    const count = cols * rows;
    gridItems = shuffled(artworkIDs).slice(0, count);
  }

  let resizeTimer;
  function handleResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      computeGrid();
      generate();
    }, 150);
  }

  let gridEl;

  onMount(() => {
    computeGrid();
    generate();
    window.addEventListener('resize', handleResize);
    // Non-passive so we can conditionally preventDefault to block synthetic click after swipe
    gridEl.addEventListener('touchend', handleGridTouchEnd, { passive: false });
    return () => {
      window.removeEventListener('resize', handleResize);
      clearTimeout(resizeTimer);
      gridEl?.removeEventListener('touchend', handleGridTouchEnd);
    };
  });

  // Touch two-tap: first tap scales, second tap navigates.
  // Mouse clicks navigate immediately (hover already gives preview).
  let activeID = null;
  let lastPointerType = 'mouse';

  // Swipe-hover: tracks which cell is under the finger during a drag.
  let swipeHoverID = null;
  let touchStartX = 0;
  let touchStartY = 0;
  let touchMoved = false;
  const SWIPE_THRESHOLD = 6;

  function handleGridTouchStart(e) {
    const t = e.touches[0];
    touchStartX = t.clientX;
    touchStartY = t.clientY;
    touchMoved = false;
  }

  function handleGridTouchMove(e) {
    const t = e.touches[0];
    const dx = t.clientX - touchStartX;
    const dy = t.clientY - touchStartY;
    if (!touchMoved && Math.sqrt(dx * dx + dy * dy) > SWIPE_THRESHOLD) {
      touchMoved = true;
      activeID = null; // clear any pending tap
    }
    if (touchMoved) {
      const el = document.elementFromPoint(t.clientX, t.clientY);
      const cell = el?.closest('[data-id]');
      swipeHoverID = (cell instanceof HTMLElement ? cell.dataset.id : null) ?? null;
    }
  }

  function handleGridTouchEnd(e) {
    if (touchMoved) {
      e.preventDefault(); // block synthetic mouse/click events after swipe
      swipeHoverID = null;
      touchMoved = false;
    }
  }

  function handlePointerDown(e) {
    lastPointerType = e.pointerType;
  }

  function handleCellClick(id) {
    if (touchMoved) { touchMoved = false; return; } // safety guard
    if (lastPointerType === 'touch') {
      if (activeID === id) {
        dispatch('select', id);
        activeID = null;
      } else {
        activeID = id;
      }
    } else {
      dispatch('select', id);
    }
  }

  function handleWrapClick(e) {
    if (!e.target.closest('.cell')) activeID = null;
  }
</script>

<div class="microfiche-wrap" role="presentation" on:click={handleWrapClick} on:keydown={() => {}}>
  <div
    class="microfiche-grid"
    style="grid-template-columns: repeat({cols}, 30px)"
    bind:this={gridEl}
    on:touchstart={handleGridTouchStart}
    on:touchmove={handleGridTouchMove}
  >
    {#each gridItems as id (id)}
      <button
        class="cell"
        class:active={id === activeID}
        class:swipe-hover={id === swipeHoverID}
        data-id={id}
        on:pointerdown={handlePointerDown}
        on:click={() => handleCellClick(id)}
        aria-label="View artwork {id}"
      >
        <img src="thumbs/{id}.webp" alt="" loading="lazy" on:error={e => { if (e.currentTarget instanceof HTMLElement) e.currentTarget.style.visibility = 'hidden'; }} />
      </button>
    {/each}
  </div>
  <div class="controls">
    <button class="regen-btn" on:click={generate}>Regenerate</button>
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

  .cell:hover {
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

  .cell:hover img,
  .cell.active img,
  .cell.swipe-hover img {
    transform: scale(1.6);
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
