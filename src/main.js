import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

// Pre-fetch artwork IDs before mounting the app to reduce LCP
// This happens in parallel with Svelte framework initialization
// If this fails, App.svelte will fall back to its own fetch
window.artworkIDsPromise = fetch('artworkids.json')
  .then(r => r.json())
  .catch(err => {
    console.warn('Pre-fetch of artworkids.json failed:', err);
    return null;
  });

const app = mount(App, {
  target: document.getElementById('app'),
})

export default app
