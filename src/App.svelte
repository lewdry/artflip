<script>
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';

  let artwork = null;
  let loading = true;
  let error = null;
  let artworkIDs = [];

  // Rate limiting to be respectful to GitHub/Cloudflare 
  let lastRequestTime = 0;
  const MIN_REQUEST_INTERVAL = 100; // 100ms between requests

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
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout
    
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

  /**
   * Fetches a random artwork from local JSON files
   */
  async function fetchRandomArtwork() {
    loading = true;
    error = null;
    
    try {
      let attempts = 0;
      const maxAttempts = 3;
      
      while (attempts < maxAttempts) {
        try {
          // Select a random ID from our curated list
          const randomID = artworkIDs[Math.floor(Math.random() * artworkIDs.length)];
          console.log(`Fetching artwork ${randomID} (attempt ${attempts + 1})`);
          
          // Fetch metadata from local JSON file
          const metadataUrl = `metadata/${randomID}.json`;
          const artworkData = await rateLimitedFetch(metadataUrl);
          
          // Validate we got good data
          if (!artworkData || !artworkData.localImage) {
            throw new Error('Invalid artwork data');
          }
          
          // Set local image path
          artworkData.displayImage = `images/${artworkData.localImage}`;
          
          artwork = artworkData;
          console.log('Successfully loaded:', artworkData.title);
          return; // Success!
          
        } catch (attemptError) {
          console.warn(`Attempt ${attempts + 1} failed:`, attemptError);
          attempts++;
          
          // If this was the last attempt, throw the error
          if (attempts >= maxAttempts) {
            throw new Error('Unable to load artwork after multiple attempts');
          }
        }
      }
      
    } catch (err) {
      error = err.message;
      console.error('Error fetching artwork:', err);
    } finally {
      loading = false;
    }
  }

  // Handle image loading errors (fallback in case image file is missing)
  function handleImageError(event) {
    console.error('Image failed to load:', artwork?.localImage);
    error = 'Image failed to load. Please try another artwork.';
  }

  onMount(async () => {
  artworkIDs = await rateLimitedFetch('artworkids.json');
  fetchRandomArtwork();
  });


  // Conditional museum button text
  function getMuseumButtonText(creditLine) {
    if (!creditLine) {
      return "View on Museum Site →";
    } else if (creditLine.startsWith("Metropolitan")) {
      return "View on the Met Site →";
    } else if (creditLine.startsWith("Art Institute of Chicago")) {
      return "View on the AIC Site →";
    } else {
      return "View on Museum Site →";
    }
  }
</script>

<main>
  <div class="container">
    <header>
      <div class="title-group">
        <h1>ArtFlip</h1>
        <h2>Random public domain artworks.</h2>
      </div>

      <button on:click={fetchRandomArtwork} disabled={loading} class="refresh-btn">
        {#if loading && artwork} 
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
      {#key artwork.objectID}
        <article class="artwork" in:fade={{ duration: 400, delay: 100 }}>
          <div class="image-container">
            <img 
              src={artwork.displayImage}
              alt={artwork.title || 'Artwork'}
              loading="lazy"
              on:error={handleImageError}
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
              <a href={artwork.objectURL} target="_blank" rel="noopener noreferrer" class="museum-link">
                View on Museum Site →
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
        All artwork displayed here is public domain, available under Creative Commons.<br>
        <a href="https://lewisdryburgh.com" target="_blank" rel="noopener noreferrer">Lewis Dryburgh</a>, 2025
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
    align-items: flex-start;
    margin-bottom: 2rem;
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
    font-size: 1.2rem;
    margin: 0 0 0.2rem 0;
    font-weight: 700;
  }

  .title-group h2 {
    font-size: 0.9rem;
    margin: 0;
    font-style: italic;
    color: #555;
    font-weight: 400;
    text-align: left;
    width: 100%;
    word-wrap: break-word;
    line-height: 1.3;
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
    flex-shrink: 0;
    white-space: nowrap;
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
    font-weight: 500;
  }

  .retry-btn:hover { 
    background: #c82333; 
  }

  .artwork {
    background: white;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
    display: grid;
    max-width: 100%;
  }

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
    object-fit: contain;
    background: #fff;
    max-height: 80vh;
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

  footer {
    margin-top: 3rem;
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