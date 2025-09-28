<script>
  import { onMount } from 'svelte';

  let artwork = null;
  let loading = false;
  let error = null;

  // Backup object IDs in case proxies fail
  const fallbackObjectIDs = [
    436532, 459080, 437853, 436105, 459055, 338059, 459054, 437329, 
    438817, 459053, 437894, 459052, 436963, 459051, 437392, 438813,
    11734, 436535, 459049, 438807, 437853, 459048, 436951, 438801,
    459047, 437882, 436954, 459046, 438796, 437876, 459045, 436943,
    438787, 459044, 437865, 436932, 459043, 438778, 437858, 459042,
    436925, 438769, 459041, 437851, 436918, 459040, 438760, 437844,
    459039, 436911, 438751, 459038, 437837, 436904, 459037, 438742,
    10467, 272099, 459074, 39799, 471596, 459073, 36647, 438635,
    459072, 38065, 438629, 459071, 37858, 438623, 459070, 37851,
    367069, 436516, 459069, 438617, 367076, 436509, 459068, 438611,
    367083, 436502, 459067, 438605, 367090, 436495, 459066, 438599,
    11150, 437379, 459065, 438593, 11157, 437372, 459064, 438587
  ];

  // Function to get optimized image URL
  function getOptimizedImageUrl(originalUrl) {
    if (!originalUrl) return '';
    
    // Met Museum images can be resized by adding parameters
    // Original: https://images.metmuseum.org/CRDImages/as/original/DP251139.jpg
    // Resized: https://images.metmuseum.org/CRDImages/as/web-large/DP251139.jpg
    
    // Replace 'original' with 'web-large' for faster loading (about 1200px wide)
    // or use 'web-medium' for even smaller (about 800px wide)
    return originalUrl.replace('/original/', '/web-large/');
  }

  // Cache for search results and rate limiting
  let cachedObjectIDs = null;
  let lastSearchTime = 0;
  let lastRequestTime = 0;
  const CACHE_DURATION = 10 * 60 * 1000; // 10 minutes
  const MIN_REQUEST_INTERVAL = 2000; // 2 seconds between requests

  async function rateLimitedFetch(url) {
    // Enforce minimum time between requests
    const now = Date.now();
    const timeSinceLastRequest = now - lastRequestTime;
    
    if (timeSinceLastRequest < MIN_REQUEST_INTERVAL) {
      await new Promise(resolve => 
        setTimeout(resolve, MIN_REQUEST_INTERVAL - timeSinceLastRequest)
      );
    }
    
    lastRequestTime = Date.now();
    
    // Try direct API call first (might work without VPN)
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);
      
      const response = await fetch(url, { 
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (response.ok) {
        return await response.json();
      }
    } catch (directError) {
      console.log('Direct API failed, trying proxies...');
    }
    
    // Fallback to single reliable proxy
    const corsProxy = 'https://api.allorigins.win/get?url=';
    const proxyUrl = `${corsProxy}${encodeURIComponent(url)}`;
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);
    
    const response = await fetch(proxyUrl, { 
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      throw new Error(`Proxy failed: ${response.status}`);
    }
    
    const text = await response.text();
    
    if (text.trim().startsWith('<')) {
      throw new Error('Received HTML error page');
    }
    
    const proxyData = JSON.parse(text);
    return JSON.parse(proxyData.contents);
  }

  async function getObjectIDs() {
    // Use cached results if they're recent
    if (cachedObjectIDs && Date.now() - lastSearchTime < CACHE_DURATION) {
      console.log('Using cached search results');
      return cachedObjectIDs;
    }

    try {
      console.log('Fetching fresh search results...');
      const searchUrl = 'https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q=*';
      const searchData = await rateLimitedFetch(searchUrl);
      
      if (searchData?.objectIDs && searchData.objectIDs.length > 0) {
        cachedObjectIDs = searchData.objectIDs;
        lastSearchTime = Date.now();
        console.log(`Cached ${searchData.objectIDs.length} object IDs`);
        return cachedObjectIDs;
      }
      
    } catch (searchError) {
      console.warn('Search failed:', searchError);
    }
    
    // If search failed, use fallback
    console.log('Using fallback object IDs');
    return fallbackObjectIDs;
  }

  async function fetchRandomArtwork() {
    loading = true;
    error = null;
    
    try {
      // Get object IDs (from cache, search, or fallback)
      const objectIDs = await getObjectIDs();
      
      // Try up to 3 random artworks to find one that's public domain
      let attempts = 0;
      const maxAttempts = 3;
      
      while (attempts < maxAttempts) {
        try {
          // Pick a random object ID
          const randomId = objectIDs[Math.floor(Math.random() * objectIDs.length)];
          
          console.log(`Fetching artwork ${randomId} (attempt ${attempts + 1})`);
          
          const apiUrl = `https://collectionapi.metmuseum.org/public/collection/v1/objects/${randomId}`;
          const artworkData = await rateLimitedFetch(apiUrl);
          
          if (!artworkData) {
            attempts++;
            continue;
          }
          
          // Only check if it's public domain (trust API for hasImages)
          if (artworkData.isPublicDomain && artworkData.primaryImage) {
            // Log ALL available fields to help identify description field
            console.log('ALL artwork fields:', artworkData);
            
            artwork = artworkData;
            console.log('Successfully loaded artwork:', artworkData.title);
            return; // Success! Exit the function
          }
          
          console.log('Artwork not public domain, trying another...');
          attempts++;
          
        } catch (attemptError) {
          console.warn(`Attempt ${attempts + 1} failed:`, attemptError);
          attempts++;
        }
      }
      
      // If we get here, we couldn't find a public domain artwork after maxAttempts
      throw new Error(`Could not find a suitable artwork after ${maxAttempts} attempts`);
      
    } catch (err) {
      error = `Unable to fetch artwork: ${err.message}`;
      console.error('Fetch error:', err);
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    fetchRandomArtwork();
  });
</script>

<main>
  <div class="container">
    <header>
      <h1>RandyMet - Met Museum Explorer</h1>
      <button on:click={fetchRandomArtwork} disabled={loading} class="refresh-btn">
        {#if loading}
          <span class="spinner"></span>
        {:else}
          New Artwork
        {/if}
      </button>
    </header>

    {#if error}
      <div class="error">
        <p>Sorry, something went wrong: {error}</p>
        <button on:click={fetchRandomArtwork} class="retry-btn">Try Again</button>
      </div>
    {:else if artwork}
      <article class="artwork">
        <div class="image-container">
          <img 
            src={getOptimizedImageUrl(artwork.primaryImage)} 
            alt={artwork.title || 'Artwork'}
            loading="lazy"
          />
        </div>
        
        <div class="metadata">
          <h2 class="title">{artwork.title || 'Untitled'}</h2>
          
          {#if artwork.artistDisplayName}
            <p class="artist">{artwork.artistDisplayName}</p>
          {/if}
          
          <div class="details">
            {#if artwork.objectDate}
              <p class="date">{artwork.objectDate}</p>
            {/if}
            
            {#if artwork.medium}
              <p class="medium">{artwork.medium}</p>
            {/if}
            
            {#if artwork.department}
              <p class="department">{artwork.department}</p>
            {/if}

            {#if artwork.culture}
              <p class="culture">{artwork.culture}</p>
            {/if}

            {#if artwork.period}
              <p class="period">{artwork.period}</p>
            {/if}
          </div>
          
          {#if artwork.objectURL}
            <a href={artwork.objectURL} target="_blank" rel="noopener noreferrer" class="museum-link">
              View on Met Museum Website →
            </a>
          {/if}
        </div>
      </article>
    {/if}
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #fafafa;
  }

  .container {
    max-width: 100vw;
    min-height: 100vh;
    padding: 1rem;
    box-sizing: border-box;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #e0e0e0;
  }

  h1 {
    font-size: 1.2rem;
    font-weight: 600;
    margin: 0;
    color: #2c2c2c;
  }

  .refresh-btn {
    background: #007acc;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .refresh-btn:hover:not(:disabled) {
    background: #005a99;
    transform: translateY(-1px);
  }

  .refresh-btn:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid transparent;
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .error {
    text-align: center;
    padding: 2rem;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  }

  .retry-btn {
    background: #dc3545;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    margin-top: 1rem;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .retry-btn:hover {
    background: #c82333;
  }

  .artwork {
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    max-width: 100%;
  }

  .image-container {
    width: 100%;
    position: relative;
    background: #f8f9fa;
  }

  .image-container img {
    width: 100%;
    height: auto;
    display: block;
    object-fit: cover;
    max-height: 70vh;
  }

  .metadata {
    padding: 1.5rem;
  }

  .title {
    font-size: 1.4rem;
    font-weight: 600;
    margin: 0 0 0.5rem 0;
    color: #1a1a1a;
    line-height: 1.3;
  }

  .artist {
    font-size: 1.1rem;
    color: #666;
    margin: 0 0 1rem 0;
    font-style: italic;
  }

  .details {
    margin-bottom: 1.5rem;
  }

  .details p {
    margin: 0.5rem 0;
    font-size: 0.9rem;
    color: #555;
  }

  .date {
    font-weight: 500;
    color: #444;
  }

  .medium {
    color: #666;
  }

  .culture {
    color: #555;
    font-style: italic;
  }

  .period {
    color: #666;
    font-size: 0.9rem;
  }

  .department {
    color: #888;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 500;
  }



  .museum-link {
    display: inline-block;
    color: #007acc;
    text-decoration: none;
    font-weight: 500;
    font-size: 0.9rem;
    border: 1px solid #007acc;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    transition: all 0.2s ease;
  }

  .museum-link:hover {
    background: #007acc;
    color: white;
    transform: translateY(-1px);
  }

  /* Mobile optimizations */
  @media (max-width: 480px) {
    .container {
      padding: 0.75rem;
    }

    h1 {
      font-size: 1.1rem;
    }

    .refresh-btn {
      font-size: 0.8rem;
      padding: 0.4rem 0.8rem;
    }

    .metadata {
      padding: 1.25rem;
    }

    .title {
      font-size: 1.2rem;
    }

    .artist {
      font-size: 1rem;
    }
  }

  /* iPhone-specific optimizations */
  @media (max-width: 390px) {
    .image-container img {
      max-height: 60vh;
    }
  }
</style>