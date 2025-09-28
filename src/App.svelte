<script>
  import { onMount } from 'svelte';

  let artwork = null;
  let loading = false;
  let error = null;

  async function fetchRandomArtwork() {
    loading = true;
    error = null;
    
    try {
      // First, get all object IDs
      const searchResponse = await fetch('https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q=*');
      const searchData = await searchResponse.json();
      
      if (!searchData.objectIDs || searchData.objectIDs.length === 0) {
        throw new Error('No artworks found');
      }
      
      // Pick a random object ID
      const randomId = searchData.objectIDs[Math.floor(Math.random() * searchData.objectIDs.length)];
      
      // Fetch the specific artwork
      const artworkResponse = await fetch(`https://collectionapi.metmuseum.org/public/collection/v1/objects/${randomId}`);
      const artworkData = await artworkResponse.json();
      
      // Make sure it has an image AND is Open Access (CC0)
      if (!artworkData.primaryImage || !artworkData.isPublicDomain) {
        // If no image or not public domain, try again
        fetchRandomArtwork();
        return;
      }
      
      artwork = artworkData;
    } catch (err) {
      error = err.message;
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
      <h1>Met Museum Explorer</h1>
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
            src={artwork.primaryImage} 
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
            
            {#if artwork.dimensions}
              <p class="dimensions">{artwork.dimensions}</p>
            {/if}
            
            {#if artwork.department}
              <p class="department">{artwork.department}</p>
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
    font-size: 1.5rem;
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

  .dimensions {
    color: #777;
    font-size: 0.85rem;
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
      font-size: 1.3rem;
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