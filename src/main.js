import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

// Pre-fetch artwork IDs before mounting the app to reduce LCP
// This happens in parallel with Svelte framework initialization
window.artworkIDsPromise = fetch('artworkids.json').then(r => r.json());

const app = mount(App, {
  target: document.getElementById('app'),
})

export default app
