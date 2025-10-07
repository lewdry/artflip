# ArtFlip

**ArtFlip** is a clean, modern Svelte application that delivers a continuous stream of random artworks from **public domain art collections**. Discover masterpieces and hidden gems one flip at a time.

---

## ✨ Features

* **Random Art Discovery:** Instantly loads a random public domain image on launch and on refresh.
* **Intuitive Navigation:** Flip between previous and next artworks by:
    * **Clicking/Tapping** the left or right edge of the image.
    * Using the **$\leftarrow$ Left** and **$\rightarrow$ Right** arrow keys.
    * **Swiping** left or right on touch devices.
* **Preloading & History:** ArtFlip efficiently preloads upcoming images and maintains a local history (up to 20 past works) for seamless navigation without repeated fetching.
* **Deep Links:** Shares state via the URL, allowing you to share a direct link to the currently displayed artwork.
* **Full Metadata:** Displays key information including the artist, title, date, medium, and a direct link to the source museum.

## Current Count  of artworks - 2025/10/07
1. Metropolitan Museum of Art 2439
2. Art Institute of Chicago 1977
3. Rijksmuseum 692

---

## 🛠️ Installation

This project is built with **Svelte** and relies on JSON files for artwork metadata and IDs, and corresponding jpg images.

### Prerequisites

* Node.js (LTS recommended)
* npm or yarn

### Setup Steps

1.  **Clone the Repository:**
    ```bash
    git clone [your-repository-url]
    cd ArtFlip
    ```

2.  **Install Dependencies:**
    ```bash
    npm install
    # or
    yarn install
    ```

3.  **Data Structure (Crucial):**
    The app expects two data sources in the root directory (or served path):
    * `artworkids.json`: An array of all valid `objectID`s (e.g., `[123, 456, 789, ...]`).
    * `metadata/{objectID}.json`: A folder containing individual JSON files for each artwork, named by their ID (e.g., `metadata/123.json`). Each file must contain a `localImage` field pointing to the image path (e.g., `images/{localImage}`).

4.  **Run Locally:**
    ```bash
    npm run dev
    # or
    yarn dev
    ```
    The application will be available at `http://localhost:5173` (or a similar port).

---

## ⚙️ Configuration

Key constants can be configured directly in the main component's `<script>` block:

| Constant | Description | Default Value |
| :--- | :--- | :--- |
| `MAX_HISTORY` | The total number of artworks (past + current + future) to keep in memory before trimming old history. | `24` |
| `PRELOAD_COUNT` | The number of artworks to proactively load ahead of the current view. | `3` |
| `COOLDOWN_DURATION` | Milliseconds to wait after a navigation event before allowing another to prevent rapid-fire clicks. | `750` |
| `NAVIGATION_ZONE_THRESHOLD` | Defines the clickable/swipable area for previous/next navigation as a fraction of the image width. | `0.33` (i.e., the outer 33%) |

---

## 📜 Public Domain Art

All art displayed is sourced from collections that have dedicated their works to the public domain, making them available under a **Creative Commons Zero (CC0)** dedication. This typically means the works are free of known copyright restrictions.

The application itself makes no claims on the artwork images or metadata. It is an interface for discovery.