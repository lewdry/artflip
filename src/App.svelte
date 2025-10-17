<script>
  import { onMount, onDestroy } from 'svelte';
  import { fade } from 'svelte/transition';

  // Configuration
  const MAX_HISTORY = 24; // 20 back + 1 current + 3 forward
  const PRELOAD_COUNT = 3; // Number of artworks to keep preloaded ahead
  const COOLDOWN_DURATION = 750; // ms
  const PRELOAD_DELAY = 200; // ms between preload requests
  const NAVIGATION_ZONE_THRESHOLD = 0.33; // Configurable thirds (0.33 = 1/3)

  // State
  let artworks = [];
  let currentIndex = 0;
  let loading = true;
  let error = null;
  let artworkIDs = [];
  let seenIDs = new Set(); // Track artworks shown this session
  let isCoolingDown = false;
  let isPreloading = false;
  let copied = false;

  // Rate limiting
  let lastRequestTime = 0;
  const MIN_REQUEST_INTERVAL = 100;

  async function rateLimitedFetch(url) {
    const now = Date.now();
    const timeSinceLastRequest = now - lastRequestTime;
    
    if (timeSinceLastRequest < MIN_REQUEST_INTERVAL) {
      await new Promise(resolve => 
        setTimeout(resolve, MIN_REQUEST_INTERVAL - timeSinceLastRequest)
      );
    }
    
    lastRequestTime = Date.now();
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    
    try {
      const response = await fetch(url, { signal: controller.signal });
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        throw new Error(`Failed to load: ${response.status}`);
      }
      
      return await response.json();
    } catch (err) {
      clearTimeout(timeoutId);
      throw err;
    }
  }

  function updateURL(objectID) {
    if (objectID && window.history && window.history.pushState) {
      const url = new URL(window.location.href);
      url.searchParams.set('id', objectID);
      window.history.pushState({ artworkID: objectID }, '', url);
    }
  }

  function getArtworkIDFromURL() {
    const params = new URLSearchParams(window.location.search);
    return params.get('id');
  }

  function preloadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve();
      img.onerror = reject;
      img.src = src;
    });
  }

  async function fetchSingleArtwork(objectID = null) {
    try {
      // If no ID provided, get a random one that hasn't been seen
      if (!objectID) {
        const availableIDs = artworkIDs.filter(id => !seenIDs.has(id));
        if (availableIDs.length === 0) {
          // If all seen, reset and start over
          seenIDs.clear();
          artworkIDs.forEach(id => seenIDs.delete(id));
        }
        const unseenIDs = artworkIDs.filter(id => !seenIDs.has(id));
        objectID = unseenIDs[Math.floor(Math.random() * unseenIDs.length)];
      }
      
      console.log(`Fetching artwork ${objectID}`);
      
      const metadataUrl = `metadata/${objectID}.json`;
      const artworkData = await rateLimitedFetch(metadataUrl);
      
      if (!artworkData || !artworkData.localImage) {
        throw new Error('Invalid artwork data');
      }
      
      artworkData.displayImage = `images/${artworkData.localImage}`;
      await preloadImage(artworkData.displayImage);
      
      seenIDs.add(objectID);
      console.log('Successfully loaded:', artworkData.title);
      
      return artworkData;
      
    } catch (err) {
      console.error('Error fetching artwork:', err);
      throw err;
    }
  }

  async function preloadNextArtworks() {
    if (isPreloading) return;
    isPreloading = true;

    try {
      const neededCount = PRELOAD_COUNT - (artworks.length - currentIndex - 1);
      
      for (let i = 0; i < neededCount; i++) {
        try {
          await new Promise(resolve => setTimeout(resolve, PRELOAD_DELAY));
          const newArtwork = await fetchSingleArtwork();
          artworks = [...artworks, newArtwork];
          trimHistory(); // Trim after each addition
          console.log(`Preloaded artwork. Array size: ${artworks.length}, Current index: ${currentIndex}`);
        } catch (err) {
          console.warn('Failed to preload, trying another:', err);
          i--; // Retry with a different artwork
        }
      }
    } finally {
      isPreloading = false;
    }
  }

  function trimHistory() {
    if (artworks.length > MAX_HISTORY) {
      const excess = artworks.length - MAX_HISTORY;
      artworks = artworks.slice(excess);
      currentIndex = currentIndex - excess;
      console.log(`Trimmed ${excess} old artworks. Now at index ${currentIndex}/${artworks.length}`);
    }
  }

  async function nextArtwork() {
    if (isCoolingDown) return;
    
    if (currentIndex < artworks.length - 1) {
      // Move to next existing artwork
      currentIndex++;
      updateURL(artworks[currentIndex].objectID);
      startCooldown();
      preloadNextArtworks(); // Ensure we have enough preloaded
    } else {
      // Need to fetch a new one
      loading = true;
      try {
        const newArtwork = await fetchSingleArtwork();
        artworks = [...artworks, newArtwork];
        currentIndex = artworks.length - 1;
        
        trimHistory();
        updateURL(newArtwork.objectID);
        startCooldown();
        preloadNextArtworks();
      } catch (err) {
        error = 'Unable to load next artwork';
        setTimeout(() => error = null, 3000);
      } finally {
        loading = false;
      }
    }
  }

  function prevArtwork() {
    if (isCoolingDown || currentIndex <= 0) return;
    
    currentIndex--;
    updateURL(artworks[currentIndex].objectID);
    startCooldown();
  }

  function startCooldown() {
    isCoolingDown = true;
    setTimeout(() => {
      isCoolingDown = false;
    }, COOLDOWN_DURATION);
  }

  function handleImageClick(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickedThird = clickX / rect.width;

    if (clickedThird < NAVIGATION_ZONE_THRESHOLD) {
      event.preventDefault();
      prevArtwork();
    } else if (clickedThird > (1 - NAVIGATION_ZONE_THRESHOLD)) {
      event.preventDefault();
      nextArtwork();
    }
    // Middle third: do nothing, allow default browser behavior
  }

  function handleImageMouseMove(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const moveX = event.clientX - rect.left;
    const zone = moveX / rect.width;

    if (zone < NAVIGATION_ZONE_THRESHOLD && currentIndex > 0) {
      event.currentTarget.style.cursor = 'w-resize';
    } else if (zone > (1 - NAVIGATION_ZONE_THRESHOLD)) {
      event.currentTarget.style.cursor = 'e-resize';
    } else {
      event.currentTarget.style.cursor = 'default';
    }
  }

  function handleKeydown(event) {
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') return;
    
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      prevArtwork();
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      nextArtwork();
    }
  }

  function handlePopState(event) {
    const urlID = getArtworkIDFromURL();
    if (urlID) {
      // Find this artwork in our history
      const index = artworks.findIndex(a => a.objectID === urlID);
      if (index !== -1) {
        currentIndex = index;
      }
    }
  }

  function handleImageError(event) {
    console.error('Image failed to load');
    error = 'Image failed to load. Please try another artwork.';
    setTimeout(() => error = null, 3000);
  }

  // Touch/swipe support
  let touchStartX = 0;
  let touchEndX = 0;
  const SWIPE_THRESHOLD = 60;

  function handleTouchStart(event) {
    touchStartX = event.changedTouches[0].screenX;
  }

  function handleTouchEnd(event) {
    touchEndX = event.changedTouches[0].screenX;
    handleSwipe();
  }

  function handleSwipe() {
    const diff = touchStartX - touchEndX;
    
    if (Math.abs(diff) > SWIPE_THRESHOLD) {
      if (diff > 0) {
        // Swiped left - next artwork
        nextArtwork();
      } else {
        // Swiped right - previous artwork
        prevArtwork();
      }
    }
  }

  onMount(() => {
    // Add keyboard listener
    window.addEventListener('keydown', handleKeydown);
    window.addEventListener('popstate', handlePopState);

    // Load initial artwork
    (async () => {
      artworkIDs = await rateLimitedFetch('artworkids.json');
      
      const urlID = getArtworkIDFromURL();
      
      try {
        if (urlID) {
          // Load specific artwork from URL
          const artwork = await fetchSingleArtwork(urlID);
          artworks = [artwork];
          currentIndex = 0;
        } else {
          // Load random initial artwork
          const artwork = await fetchSingleArtwork();
          artworks = [artwork];
          currentIndex = 0;
          updateURL(artwork.objectID);
        }
        
        // Preload next artworks
        preloadNextArtworks();
      } catch (err) {
        error = 'Unable to load artwork';
      } finally {
        loading = false;
      }
    })();

    return () => {
      window.removeEventListener('keydown', handleKeydown);
      window.removeEventListener('popstate', handlePopState);
    };
  });

  onDestroy(() => {
    window.removeEventListener('keydown', handleKeydown);
    window.removeEventListener('popstate', handlePopState);
  });

  $: artwork = artworks[currentIndex];

  // Ensure 'copied' resets whenever we show a different artwork
  $: if (artworks && artworks.length) {
    // when currentIndex or artworks changes, clear copied state
    copied = false;
  }
</script>

<main>
  <div class="container">
    <header>
      <div class="title-group">
        <h1>Artflip.</h1>
        <h2>Public domain art</h2>
      </div>

      <button on:click={nextArtwork} disabled={isCoolingDown || loading} class="refresh-btn">
        {#if loading && artwork} 
          <span class="spinner"></span>
        {:else}
          New Artwork
        {/if}
      </button>
    </header>

    {#if error}
      <div class="error">
        <p>{error}</p>
      </div>
    {:else if artwork}
      {#key artwork.objectID}
        <article class="artwork" in:fade={{ duration: 400, delay: 100 }}>
          <div 
            class="image-container"
            role="button"
            tabindex="0"
            aria-label="Click left or right to navigate artworks"
            on:click={handleImageClick}
            on:keydown={handleImageClick}
            on:mousemove={handleImageMouseMove}
            on:touchstart={handleTouchStart}
            on:touchend={handleTouchEnd}
          >
            <img 
              src={artwork.displayImage}
              alt={artwork.title || 'Artwork'}
              on:error={handleImageError}
            />
          </div>
          
          <div class="metadata">
            <h2 class="title">{artwork.title || 'Untitled'}</h2>
            
            {#if artwork.artistDisplayName}
              <p class="artist">{artwork.artistDisplayName || 'Artist Unknown'}</p>
            {/if}
            
            <div class="details">
             <!-- {#if artwork.objectName}
                <p><strong>Type:</strong> {artwork.objectName}</p>
              {/if} -->

              {#if artwork.objectDate}
                <p><strong></strong> {artwork.objectDate}</p> <!-- removed Date:-->
              {/if}
              
              {#if artwork.medium}
                <p><strong>Medium:</strong> {artwork.medium}</p>
              {/if}

              {#if artwork.culture}
                <p><strong>Culture:</strong> {artwork.culture}</p>
              {/if}

              {#if artwork.period}
                <p><strong>Period:</strong> {artwork.period}</p>
              {/if}
              
              {#if artwork.department}
                <p class="department">{artwork.department}</p>
              {/if}
            </div>

            {#if artwork.creditLine}
              <p class="credit-line">{artwork.creditLine}</p>
            {/if}
            
            {#if artwork.objectURL}
                <div class="link-buttons">
                  <button class="copy-link-btn" on:click={async () => { try { await navigator.clipboard.writeText(window.location.href); copied = true; setTimeout(() => copied = false, 1100); } catch (e) { error = 'Unable to copy link'; setTimeout(() => error = null, 3000); } }}>
                    {#if copied}
                      Link Copied ✓
                    {:else}
                      Copy Link to Clipboard
                    {/if}
                  </button>

                  <a href={artwork.objectURL} target="_blank" rel="noopener noreferrer" class="museum-link">
                    View on Museum Site →
                  </a>
                </div>
            {/if}
          </div>
        </article>
      {/key}
    {:else if loading}
      <div class="initial-loader">
        <span class="spinner"></span>
        <p>Finding a masterpiece...</p>
      </div>
    {/if}
    <footer>
      <p class="footer-credit">
        All artworks displayed are in the public domain, available under Creative Commons Zero.<br>
        Artflip by <a href="https://lewisdryburgh.com/2025/10/13/artflip" target="_blank" rel="noopener noreferrer">Lewis Dryburgh</a>, 2025
      </p>
      <a href="https://instagram.com/artflip.me" target="_blank" rel="noopener noreferrer" class="instagram-link" aria-label="Follow on Instagram">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
          <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
          <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
        </svg>
      </a>
    </footer>
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: #333;
    background: linear-gradient(180deg, #fff 0%, #f9f9fb 100%); /* softer gradient background */
  }

  .container {
    max-width: 1000px;
    margin: 0 auto;
    padding: 1.5rem 1rem;
    box-sizing: border-box;
    min-height: 100vh;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem; /* slightly more breathing room */
    gap: 1rem;
  }

  .title-group {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    flex: 1;
    min-width: 0;
  }

  .title-group h1 {
    font-size: 1.6rem; /* slightly larger for stronger identity */
    margin: 0 0 0.2rem 0;
    font-weight: 500;
    font-family: 'Josefin Sans', sans-serif;
    color: #222;
    letter-spacing: -0.25px;
  }

  .title-group h2 {
    font-size: 0.95rem;
    margin: 0;
    font-style: italic;
    color: #555;
    font-weight: 400;
    text-align: left;
    width: 100%;
    line-height: 1.4;
  }

  .refresh-btn {
    background: #131C1D;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.7rem 1.4rem; /* slightly more substantial */
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.3s ease; /* smoother animation */
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
    white-space: nowrap;
  }

  .refresh-btn:hover:not(:disabled) {
    background: #333;
    transform: scale(1.04);
    box-shadow: 0 3px 8px rgba(0,0,0,0.15);
  }

  .refresh-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .error, .initial-loader {
    text-align: center;
    padding: 4rem 2rem;
    margin-top: 2rem;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
  }

  .artwork {
    background: white;
    border-radius: 20px;
    overflow: hidden;
    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.08);
    display: grid;
    transition: box-shadow 0.2s ease;
    vertical-align: center;
  }

  .artwork:hover {
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.12);
  }

  @media (min-width: 800px) {
    .artwork {
      grid-template-columns: 1fr 1fr;
      min-width: 800px;
      width: 100%;
    }
  }

  .image-container {
    width: 100%;
    background: #f8f9fa;
    cursor: pointer;
    user-select: none;
    object-fit:contain;
    box-shadow: inset 0 0 0 1px #eee; /* faint frame */
  }

  .image-container img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: contain;
    background: #fff;
    max-height: 70vh;
  }

  .metadata {
    padding: 1.25rem 1rem;
    min-height: 300px; /* prevents collapse on short data */
    align-items: start;
  }

      /* Text clamp utility (reusable) */
  :global(.text-limit) {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    overflow: hidden;
    position: relative;
  }

  :global(.text-limit::after) {
    content: '...';
    position: absolute;
    bottom: 0;
    right: 0;
    padding-left: 30px;
    background: linear-gradient(to right, transparent, white 50%);
  }


  .title {
    font-size: 1.4rem;
    font-weight: 600;
    margin: 0 0 0.8rem 0;
    color: #111;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    overflow: hidden;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    max-height: calc(1.4em * 3);
  }

  .details {
    font-size: 0.9rem;
    margin-bottom: 0.75rem; /* more consistent rhythm */
  }

  .details p {
    margin: 0.4rem 0;
    font-size: 0.9rem;
    color: #444;
    line-height: 1.5;
  }

  .details p strong {
    font-size: 0.9rem;
    font-weight: 600;
    color: #222;
  }

  .department {
    color: #777;
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-top: 0.5rem !important;
  }

  .credit-line {
    font-size: 0.9rem;
    color: #666;
    font-style: italic;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    padding-bottom: 0.5rem;
    border-top: 1px solid #eee;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    overflow: hidden;
    -webkit-line-clamp: 5;
    line-clamp: 5;
    max-height: calc(1.5em * 5);
  }

  .museum-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #083555; /* updated museum button color */
    color: white;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.7rem 1rem;
    border-radius: 10px;
    transition: all 0.3s ease;
    box-shadow: 0 3px 8px rgba(6,42,67,0.18);
    box-sizing: border-box;
    line-height: 1.2;
    font-family: inherit;
  }

  .museum-link:hover {
    background: #052238; /* slightly darker hover for museum */
    transform: scale(1.04);
    box-shadow: 0 5px 12px rgba(5,34,56,0.28);
  }

  /* Container to stack buttons vertically and keep sizes consistent */
  .link-buttons {
    display: inline-grid;
    grid-auto-flow: row;
    grid-template-columns: 1fr; /* single column that children can fill */
    gap: 0.6rem;
    margin-top: 0.6rem;
    justify-self: center;
    justify-items: center;
    width: max-content; /* size the grid to the widest child */
  }

  .copy-link-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  background: #347c76; /* updated copy button color */
    color: white;
    border: none;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.7rem 1rem;
    border-radius: 10px;
    transition: all 0.3s ease;
    box-shadow: 0 3px 8px rgba(52,103,124,0.18);
    cursor: pointer;
    width: 100%; /* take full width of grid column so both buttons match */
    box-sizing: border-box;
    line-height: 1.2;
    font-family: inherit;
  }

  .link-buttons .museum-link {
    width: 100%;
    display: inline-flex;
    justify-content: center;
  }

  .copy-link-btn:hover:not(:disabled) {
    background: #2b6665; /* slightly darker hover for copy */
    transform: scale(1.04);
    box-shadow: 0 5px 12px rgba(43,86,102,0.28);
  }

  .copy-link-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  footer {
    margin-top: 1rem;
    text-align: left;
  }

  .footer-credit {
    font-size: 0.8rem;
    font-style: italic;
    color: #666;
    text-align: left;
    margin: 0.75rem 0 0 0;
    font-weight: 300;
  }

  .instagram-link {
    color: #666;
    transition: all 0.3s ease;
    display: inline-block;
    margin-top: 0.5rem;
  }

  .instagram-link:hover {
    color: #E4405F;
    transform: scale(1.1);
  }

  .instagram-link svg {
    display: block;
  }

  @media (max-width: 799px) {
    .container { padding: 1rem 1rem; }
    .title-group h1 { font-size: 1.3rem; }
    .metadata { padding: 1rem; }
    .title { font-size: 1.2rem; }
    .museum-link {text-align: center;}
    .details p,
    .footer-credit,
    .credit-line,
    .department {
    font-size: 0.8rem;
  }
}
</style>