<script>
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';

  let artwork = null;
  let loading = true;
  let error = null;

  // Bulletproof reliable IDs first, then other highlights  
  const publicDomainHighlights = [
    // Reliable public domain works
    436532, 459080, 437853, 436105, 459055, 338059, 459054, 437329, 438817, 459053, 
    437894, 459052, 436963, 459051, 437392, 438813, 436535, 459049, 438807, 459048, 
    436951, 438801, 459047, 437882, 436954, 459046, 438796, 437876, 459045, 436943, 
    438787, 459044, 437865, 436932, 459043, 438778, 437858, 459042, 436925, 438769, 
    459041, 437851, 436918, 459040, 438760, 437844, 459039, 436911, 438751, 459038, 
    437837, 436904, 459037, 438742, 10467, 272099, 459074, 471596, 459073, 438635, 
    459072, 438629, 459071, 438623, 459070, 367069, 436516, 459069, 438617, 367076, 
    436509, 459068, 438611, 367083, 436502, 459067, 438605, 367090, 436495, 459066, 
    438599, 437379, 459065, 438593, 437372, 459064, 438587, 435809, 435844, 435882, 
    435922, 435964, 436009, 436047, 436084, 436121, 436162, 544757, 591390, 557261, 
    557262, 557263, 557264, 557265, 437133, 437394, 438815, 438816, 438818, 438819, 
    12127, 12128, 12129, 12130, 49147, 54608,
    
    // Highlights
    200, 214, 237, 364, 458, 632, 674, 802, 1029, 1076, 1083, 1084, 1503, 1524, 
    1650, 1662, 1674, 1815, 1981, 1997, 2022, 2059, 2211, 2390, 2408, 3152, 3158, 
    3395, 3497, 3555, 4280, 4282, 4285, 4470, 4501, 4591, 4785, 4923, 5505, 5582, 
    5624, 5630, 6186, 6635, 6778, 6779, 6906, 7212, 7586, 7595, 7604, 7874, 8213, 
    8241, 8288, 9317, 9480, 9724, 9982, 10049, 10065, 10080, 10154, 10159, 10175, 
    10186, 10207, 10360, 10464, 10465, 10469, 10481, 10482, 10497, 10499, 10501, 
    10522, 10527, 10528, 10531, 10554, 10557, 10574, 10586, 10786, 10811, 10813, 
    10815, 10818, 10819, 10821, 10822, 10827, 10830, 10946, 10956, 10983, 10997, 
    11040, 11050, 11055, 11080, 11096, 11109, 11114, 11116, 11120, 11121, 11122, 
    11125, 11130, 11133, 11145, 11150, 11157, 11160, 11207, 11227, 11234, 11263, 11268, 
    11269, 11271, 11287, 11307, 11311, 11325, 11375, 11380, 11388, 11396, 11417, 
    11605, 11619, 11707, 11734, 11737, 11757, 11764, 11790, 11792, 11797, 11834, 
    11859, 11865, 11897, 11907, 11951, 11981, 11985, 11999, 12004, 12012, 12019, 
    12388, 12544, 12600, 12602, 12649, 12670, 12674, 12702, 12822, 12828, 12842, 
    12953, 13052, 13115, 13134, 13137, 13171, 13184, 13211, 13215, 13223, 13245, 
    13315, 13344, 13345, 13346, 13604, 13606, 13747, 13751, 13755, 13878, 13897, 
    13907, 14049, 14053, 14092, 14210, 14211, 14282, 14336, 14472, 14488, 14494, 
    14521, 14931, 14972, 14985, 15026, 15387, 15988, 16577, 16584, 16677, 16687, 
    16953, 17053, 17066, 17139, 17897, 18354, 19067, 19763, 20121, 20129, 20144, 
    20414, 20498, 20517, 20615, 20768, 20804, 20888, 21126, 21185, 21209, 21355, 
    21698, 21940, 22275, 22387, 22405, 22506, 22521, 22631, 22634, 22739, 22769, 
    22860, 22871, 22876, 22914, 22932, 23026, 23205, 23216, 23367, 23939, 23944, 
    23948, 24014, 24320, 24623, 24648, 24671, 24681, 24685, 24686, 24693, 24813, 
    24832, 24860, 24861, 24865, 24900, 24907, 24927, 24931, 24937, 24948, 24953, 
    24957, 24960, 24975, 25111, 27789, 27790, 27791, 27936, 35650, 36029, 36131, 
    36451, 36457, 36647, 37145, 37397, 37450, 37557, 37558, 37743, 37747, 37788, 37789, 
    37799, 37800, 37801, 37802, 37813, 37851, 37854, 37858, 37886, 37942, 37947, 37962, 37966, 
    37971, 38006, 38011, 38021, 38038, 38039, 38065, 38124, 38127, 38133, 38146, 38152, 
    38158, 38159, 38160, 38162, 38177, 38198, 38228, 38237, 38239, 38265, 38267, 
    38296, 38304, 38314, 38318, 38326, 38327, 38328, 38330, 38332, 38335, 38341, 
    38361, 38379, 38435, 38449, 38451, 38468, 38498, 38515, 38517, 38518, 38559, 
    38574, 38582, 38583, 38634, 38648, 38788, 38905, 38926, 38945, 38950, 38952, 
    38954, 38965, 38994, 39020, 39021, 39097, 39107, 39111, 39112, 39116, 39175, 
    39181, 39184, 39186, 39189, 39200, 39325, 39326, 39328, 39331, 39345, 39346, 
    39413, 39426, 39496, 39637, 39649, 39666, 39668, 39707, 39733, 39738, 39799, 39881, 
    39883, 39887, 39888, 39889, 39901, 39915, 39918, 39936, 39957, 40001, 40055, 
    40081, 40118, 40123, 40447, 40524, 40527, 40528, 42162, 42163, 42178, 42183, 
    42229, 42298, 42301, 42308, 42641, 42716, 44696, 44858, 44859, 44918, 44987, 
    45428, 45432, 48948, 49156, 50325, 50342, 50356, 50360, 50444, 50486, 50688, 
    50780, 50799, 50897, 51170, 51279, 59669, 60870, 61429, 63532, 64893, 65095, 
    65397, 65576, 65584, 72301, 72307, 72381, 72419, 72485, 72498, 72589, 72714, 
    74425, 74448, 74813, 74832, 74906, 75274, 75414, 75909, 75960, 76114, 76445, 
    76974, 78185, 78186, 78187, 78188, 78189, 78190, 78191, 78192, 78193, 78195, 
    78197, 78873, 79048, 79091, 79101, 79220, 79893, 81100, 81105, 81107, 81108, 
    81112, 81127, 81130, 81132, 81134, 81135, 81136, 81137, 81168, 81558, 81754, 
    82426, 82433, 82880, 83605, 96434, 107375, 107620, 187784, 189164, 191259, 
    191598, 191803, 191843, 192716, 192727, 192729, 193344, 193506, 193606, 193614, 
    193632, 194243, 194432, 194622, 195223, 195456, 195473, 196439, 196910, 197462, 
    198556, 198715, 199003, 199404, 199410, 199674, 199708, 199737, 200668, 201633, 
    201862, 201895, 202115, 202141, 202192, 202614, 202718, 202996, 203008, 204533, 
    204758, 204804, 204812, 204896, 205116, 205250, 205351, 205485, 205526, 206045, 
    206399, 206499, 206587, 206918, 206976, 206989, 206990, 207032, 207394, 207667, 
    207754, 207797, 208149, 208523, 208555, 208816, 209028, 209063, 209104, 209279, 
    209329, 211383, 211486, 227918, 230011, 231564, 231667, 232119, 236643, 236688, 
    236691, 239584, 242006, 242008, 242408, 243823, 245376, 245787, 247008, 247009, 
    247017, 247020, 247117, 247173, 247916, 247964, 247967, 247993, 248132, 248140, 
    248268, 248466, 248483, 248499, 248579, 248644, 248696, 248851, 248876, 248891, 
    248892, 248899, 248902, 248904, 249186, 249222, 249223, 249228, 249414, 250551, 
    250939, 250945, 250951, 251050, 251428, 251476, 251532, 251838, 251929, 251935, 
    252451, 252452, 252453, 252884, 252890, 252948, 252973, 253050, 253056, 253135, 
    253343, 253348, 253349, 253351, 253370, 253373, 253505, 253566, 253592, 254473, 
    254478, 254502, 254587, 254589, 254595, 254597, 254613, 254649, 254779, 254801, 
    254819, 254825, 254842, 254843, 254896, 254923, 255122, 255154, 255275, 255344, 
    255367, 255391, 255408, 255417, 255949, 255973, 256126, 256184, 256205, 256403, 
    256548, 256570, 256846, 256861, 256970, 256974, 256975, 256976, 256977, 256978, 
    257603, 257640, 257875, 257880, 261941, 262612, 264711, 265556, 265726, 265904, 
    266121, 266133, 266284, 266332, 266480, 266644, 266982, 266983, 267019, 267087, 
    267124, 267426, 267891, 268621, 271885, 271890, 271963, 282004, 282022, 282039, 
    282040, 282043, 282046, 282051, 282163, 282190, 282234, 282602, 282756, 283099, 
    283121, 283222, 283626, 291739
  ];

  function getOptimizedImageUrl(originalUrl) {
    if (!originalUrl) return '';
    return originalUrl.replace('/original/', '/web-large/');
  }

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

  /**
   * Fetches artwork by selecting a random ID from the public domain highlights array
   */
  async function fetchRandomArtwork() {
    loading = true;
    error = null;
    
    try {
      let attempts = 0;
      const maxAttempts = 5;
      
      while (attempts < maxAttempts) {
        try {
          // Select a random ID from our curated list
          const randomId = publicDomainHighlights[Math.floor(Math.random() * publicDomainHighlights.length)];
          console.log(`Fetching artwork with ID: ${randomId}`);
          
          const apiUrl = `https://collectionapi.metmuseum.org/public/collection/v1/objects/${randomId}`;
          const artworkData = await rateLimitedFetch(apiUrl);
          
          // Validate that we got good data
          if (artworkData?.isPublicDomain && artworkData.primaryImage) {
            artwork = artworkData;
            return; // Success, exit function
          } else {
            console.warn(`Artwork ${randomId} missing image or not public domain, trying another...`);
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
    fetchRandomArtwork();
  });
</script>

<main>
  <div class="container">
    <header>
      <div class="title-group">
        <h1>ArtFlip</h1>
        <h2>Random highlights from the Metropolitan Museum of Art.</h2>
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