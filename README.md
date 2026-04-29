# ArtFlip

A Svelte app for browsing random public domain artworks.

## Features

* Loads a random artwork on launch and refresh.
* Navigate with left/right clicks on the image edges, arrow keys, or swipes on touch devices.
* Preloads upcoming images and keeps a history of up to 20 past works.
* Deep links — the current artwork is reflected in the URL so you can share it.
* Shows artist, title, date, medium, and a link to the source museum.
* **Microfiche Mode:** Grid view of hundreds of thumbnails. Hover to zoom, click to open. On mobile, tap once to zoom, tap again to open. Use Redo to shuffle. Access directly at `/?mode=microfiche`.

## Current Count  of artworks - 2025/10/09
1. 2439 Metropolitan Museum of Art 
2. 1989 Art Institute of Chicago 
3. 1390 Rijksmuseum 

## Current Count  of artworks - 2025/10/21
 1. 2289  Metropolitan Museum of Art
 2. 1827  Art Institute of Chicago
 3. 1399  Rijksmuseum
 4. 1058  National Gallery of Art

## Current Count of artworks - 2026/04/25
  1.  2289  Metropolitan Museum of Art
  2.  1902  Art Institute of Chicago
  3.  1515  Rijksmuseum
  4.   420  Cleveland Museum of Art
  5.   410  Minneapolis Institute of Art

  Total artworks: 6575


## Installation

Requires Node.js and npm (or yarn).

```bash
git clone [your-repository-url]
cd artflip
npm install
npm run dev
```

The app will be at `http://localhost:5173`.

### Data

The app expects:
* `artworkids.json` — array of all artwork IDs, e.g. `[123, 456, ...]`
* `metadata/{id}.json` — one JSON file per artwork, must include a `localImage` field with the image path

## Configuration

These constants are in the main component's `<script>` block:

| Constant | Description | Default |
| :--- | :--- | :--- |
| `MAX_HISTORY` | Total artworks to keep in memory (past + current + future) | `24` |
| `PRELOAD_COUNT` | Number of artworks to preload ahead | `3` |
| `COOLDOWN_DURATION` | Milliseconds between allowed navigation events | `750` |
| `NAVIGATION_ZONE_THRESHOLD` | Click/swipe zone for prev/next as a fraction of image width | `0.33` |

## Public Domain Art

All artwork is from collections released under CC0. The app makes no claims on the images or metadata.

@lewdry