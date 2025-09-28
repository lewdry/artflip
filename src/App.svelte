<script>
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';

  let artwork = null;
  let loading = true;
  let error = null;

  // The API call will pick one of these at random for each new search.
  const searchTerms = [
    'cat', 'dog', 'sunflower', 'portrait', 'boat', 'water', 'france', 'japan', 
    'egypt', 'rome', 'greece', 'china', 'war', 'love', 'dragon', 'bird', 'flower', 
    'tree', 'city', 'night', 'day', 'abstract', 'modern', 'impressionism', 'renaissance', 
    'baroque', 'sculpture', 'still life', 'landscape', 'mythology', 'ocean', 'sky', 
    'music', 'ceramics', 'textiles', 'face', 'gold', 'silver', 'bronze', 'marble', 
    'religion', 'nature', 'fantasy', 'history', 'fashion', 'architecture', 'dance', 'theater', 
    'children', 'family', 'food', 'travel', 'adventure'
  ];

  // Expanded backup object IDs in case the API search fails
  const fallbackObjectIDs = [
    436532, 459080, 437853, 436105, 459055, 338059, 459054, 437329, 438817, 459053, 
    437894, 459052, 436963, 459051, 437392, 438813, 11734, 436535, 459049, 438807, 
    437853, 459048, 436951, 438801, 459047, 437882, 436954, 459046, 438796, 437876, 
    459045, 436943, 438787, 459044, 437865, 436932, 459043, 438778, 437858, 459042, 
    436925, 438769, 459041, 437851, 436918, 459040, 438760, 437844, 459039, 436911, 
    438751, 459038, 437837, 436904, 459037, 438742, 10467, 272099, 459074, 39799, 
    471596, 459073, 36647, 438635, 459072, 38065, 438629, 459071, 37858, 438623, 
    459070, 37851, 367069, 436516, 459069, 438617, 367076, 436509, 459068, 438611, 
    367083, 436502, 459067, 438605, 367090, 436495, 459066, 438599, 11150, 437379, 
    459065, 438593, 11157, 437372, 459064, 438587,
    // Additional reliable public domain works
    435809, 435844, 435882, 435922, 435964, 436009, 436047, 436084, 436121, 436162,
    // Famous Egyptian art pieces
    544757, 591390, 557261, 557262, 557263, 557264, 557265,
    // Well-known European paintings
    437133, 437394, 437853, 438815, 438816, 438817, 438818, 438819,
    // Reliable American art
    11150, 12127, 12128, 12129, 12130,
    // Asian art collection
    39733, 39799, 49147, 54608, 36647, 38065, 37858, 37851
  ];

  function getOptimizedImageUrl(originalUrl) {
    if (!originalUrl) return '';
    return originalUrl.replace('/original/', '/web-large/');
  }

  // **REMOVED** caching variables that caused the bug
  let lastRequestTime = 0;
  const MIN_REQUEST_INTERVAL = 1000;

  async function rateLimitedFetch(url) {
    const now = Date.now();
    const timeSinceLastRequest = now - lastRequestTime;
    
    if (timeSinceLastRequest < MIN_REQUEST_INTERVAL) {
      await new Promise(resolve => 
        setTimeout(resolve, MIN_REQUEST_INTERVAL - timeSinceLastRequest)
      );
    }
    
    lastRequestTime = Date.now();
    
    const corsProxy = 'https://api.allorigins.win/get?url=';
    const proxyUrl = `${corsProxy}${encodeURIComponent(url)}`;
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);
    
    const response = await fetch(proxyUrl, { signal: controller.signal });
    clearTimeout(timeoutId);
    
    if (!response.ok) {
        throw new Error(`Proxy request failed with status: ${response.status}`);
    }
    
    const proxyData = await response.json();
    if (!proxyData.contents) {
        throw new Error('Proxy response is missing "contents" field.');
    }

    return JSON.parse(proxyData.contents);
  }

  // **MODIFIED** This function no longer caches results.
  async function getObjectIDs() {
    try {
      const randomTerm = searchTerms[Math.floor(Math.random() * searchTerms.length)];
      console.log(`Searching for artworks related to: "${randomTerm}"`);

      const searchUrl = `https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q=${encodeURIComponent(randomTerm)}`;
      
      const searchData = await rateLimitedFetch(searchUrl);
      
      if (searchData?.objectIDs && searchData.objectIDs.length > 0) {
        return searchData.objectIDs;
      }
    } catch (searchError) {
      console.warn('API search failed, using fallback list.', searchError);
    }
    
    console.log('Using fallback object IDs');
    return fallbackObjectIDs;
  }
  
  /**
   * Fetches an initial artwork directly from the fallback list for a fast first load.
   */
  async function fetchInitialArtwork() {
    loading = true;
    error = null;

    try {
        let attempts = 0;
        const maxAttempts = 5;

        while (attempts < maxAttempts) {
            try {
                // Directly use a random ID from the reliable fallback list
                const randomId = fallbackObjectIDs[Math.floor(Math.random() * fallbackObjectIDs.length)];
                const apiUrl = `https://collectionapi.metmuseum.org/public/collection/v1/objects/${randomId}`;
                const artworkData = await rateLimitedFetch(apiUrl);

                if (artworkData?.isPublicDomain && artworkData.primaryImage) {
                    artwork = artworkData;
                    return; // Success, exit function
                }
                attempts++;
            } catch (attemptError) {
                console.warn(`Initial fallback fetch attempt ${attempts + 1} failed:`, attemptError);
                attempts++;
            }
        }
        throw new Error(`Could not find a suitable fallback artwork after ${maxAttempts} attempts.`);
    } catch (err) {
        error = err.message;
        console.error('Fatal error in fetchInitialArtwork:', err);
    } finally {
        loading = false;
    }
  }


  /**
   * Fetches a new artwork by first searching the API, then using fallbacks if needed.
   */
  async function fetchRandomArtwork() {
    loading = true;
    error = null;
    
    try {
      const objectIDs = await getObjectIDs();
      let attempts = 0;
      const maxAttempts = 5;
      
      while (attempts < maxAttempts) {
        try {
          const randomId = objectIDs[Math.floor(Math.random() * objectIDs.length)];
          const apiUrl = `https://collectionapi.metmuseum.org/public/collection/v1/objects/${randomId}`;
          const artworkData = await rateLimitedFetch(apiUrl);
          
          if (artworkData?.isPublicDomain && artworkData.primaryImage) {
            artwork = artworkData;
            return;
          }
          attempts++;
        } catch (attemptError) {
          console.warn(`Attempt ${attempts + 1} to fetch artwork failed:`, attemptError);
          attempts++;
        }
      }
      
      throw new Error(`Could not find a suitable artwork after ${maxAttempts} attempts.`);
      
    } catch (err) {
      error = err.message;
      console.error('Fatal error in fetchRandomArtwork:', err);
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    fetchInitialArtwork();
  });
</script>

<main>
  <div class="container">
    <header>
      <div class="title-group">
        <h1>ArtFlip</h1>
        <h2>Random art from the Metropolitan Museum.</h2>
      </div>

      <button on:click={fetchRandomArtwork} disabled={loading} class="refresh-btn">
        {#if loading && artwork} 
          <span class="spinner"></span>
        {:else}
          New Art
        {/if}
      </button>
    </header>

    {#if error}
      <div class="error">
        <p>Sorry, something went wrong: {error}</p>
        <button on:click={fetchRandomArtwork} class="retry-btn">Try Again</button>
      </div>
    {:else if artwork}
      {#key artwork.objectID}
        <article class="artwork" in:fade={{ duration: 400, delay: 100 }}>
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
              {#if artwork.objectName}
                <p><strong>Type:</strong> {artwork.objectName}</p>
              {/if}

              {#if artwork.objectDate}
                <p><strong>Date:</strong> {artwork.objectDate}</p>
              {/if}
              
              {#if artwork.medium}
                <p><strong>Medium:</strong> {artwork.medium}</p>
              {/if}
              
              {#if artwork.department}
                <p class="department">{artwork.department}</p>
              {/if}
            </div>

            {#if artwork.creditLine}
              <p class="credit-line">{artwork.creditLine}</p>
            {/if}
            
            {#if artwork.objectURL}
              <a href={artwork.objectURL} target="_blank" rel="noopener noreferrer" class="museum-link">
                View on the Met Site →
              </a>
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
        All artwork retrieved is public domain, available under Creative Commons.<br>
        Lewis Dryburgh, 2025
      </p>
    </footer>
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #f4f4f5;
  }

  .container {
    max-width: 900px;
    margin: 0 auto;
    padding: 1.5rem;
    box-sizing: border-box;
    min-height: 100vh;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start; /* Changed from center to flex-start */
    margin-bottom: 2rem;
    gap: 1rem; /* Add gap for better spacing */
  }

  .title-group {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    flex: 1; /* Allow title group to take available space */
    min-width: 0; /* Prevent flex item from overflowing */
  }

  .title-group h1 {
    font-size: 1.1rem;
    margin: 0 0 0.2rem 0;
    font-weight: 700;
  }

  .title-group h2 {
    font-size: 0.9rem;
    margin: 0;
    font-style: italic;
    color: #555;
    font-weight: 400;
    text-align: left; /* Explicitly set left alignment */
    width: 100%; /* Ensure h2 takes full width of its container */
    word-wrap: break-word; /* Allow wrapping but maintain alignment */
  }

  .refresh-btn {
    background: #1a1a1a;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.6rem 1.2rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0; /* Prevent button from shrinking */
    white-space: nowrap; /* Prevent button text from wrapping */
  }

  .refresh-btn:hover:not(:disabled) {
    background: #444;
    transform: translateY(-2px);
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
  
  header .spinner {
     border: 2px solid rgba(255, 255, 255, 0.3);
     border-top-color: white;
  }

  .initial-loader .spinner {
    display: inline-block;
    width: 32px;
    height: 32px;
    border: 3px solid rgba(0,0,0,0.1);
    border-top-color: #333;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
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

  .initial-loader p {
    margin-top: 1rem;
    color: #666;
    font-size: 1.1rem;
  }

  .retry-btn {
    background: #dc3545;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.6rem 1.2rem;
    margin-top: 1rem;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .retry-btn:hover { background: #c82333; }

  .artwork {
    background: white;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
    display: grid;
    max-width: 100%;
  }

  /* Layout changes for wider screens */
  @media (min-width: 768px) {
    .artwork {
      grid-template-columns: 1fr 1fr;
      align-items: center;
    }
  }

  .image-container {
    width: 100%;
    background: #f8f9fa;
  }

  .image-container img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: cover;
    max-height: 80vh; /* Prevents image from being too tall on mobile */
  }

  @media (min-width: 768px) {
    .image-container img {
      max-height: none;
    }
  }

  .metadata {
    padding: 2rem;
  }

  .title {
    font-size: 1.8rem;
    font-weight: 700;
    margin: 0 0 0.5rem 0;
    color: #1a1a1a;
    line-height: 1.2;
  }

  .artist {
    font-size: 1.2rem;
    color: #555;
    margin: 0 0 1.5rem 0;
  }

  .details {
    margin-bottom: 1.5rem;
    border-left: 3px solid #007acc;
    padding-left: 1rem;
  }

  .details p {
    margin: 0.5rem 0;
    font-size: 0.95rem;
    color: #444;
  }

  .details p strong {
    font-weight: 600;
    color: #1a1a1a;
  }

  .department {
    color: #888;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 1rem !important;
  }

  .credit-line {
    font-size: 0.9rem;
    color: #666;
    font-style: italic;
    margin-bottom: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid #eee;
  }

  .museum-link {
    display: inline-block;
    background: #007acc;
    color: white;
    text-decoration: none;
    font-weight: 500;
    font-size: 0.9rem;
    padding: 0.6rem 1.2rem;
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .museum-link:hover {
    background: #005a99;
    transform: scale(1.03);
  }

  .footer-credit {
    font-size: 0.8rem;
    font-style: italic;
    color: #555;
    text-align: left;
    margin: 1rem 0 0 0;
  } 

  @media (max-width: 480px) {
    .container { padding: 1rem; }
    .title-group h1 { font-size: 1.1rem; }
    .metadata { padding: 1.5rem; }
    .title { font-size: 1.5rem; }
    .artist { font-size: 1.1rem; }
    
    /* Ensure proper mobile alignment */
    header {
      align-items: flex-start;
    }
    
    .title-group {
      flex: 1;
      min-width: 0;
    }
    
    .title-group h2 {
      text-align: left;
      width: 100%;
    }
  }
</style>