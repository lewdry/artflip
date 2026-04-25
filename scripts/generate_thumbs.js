#!/usr/bin/env node
/**
 * generate_thumbs.js
 * Creates 50x50 WebP thumbnails for every image in public/images,
 * saving results to public/thumbs.
 *
 * Settings:
 *   - 50×50px, cover-crop centred (matches microfiche display)
 *   - WebP, quality 60, 4:2:0 chroma subsampling (smartSubsample: false)
 *   - Metadata stripped (Sharp default; withMetadata() is never called)
 *   - Skips files that already have an up-to-date thumbnail
 *   - Processes up to CONCURRENCY images in parallel
 */

import sharp from 'sharp';
import { readdir, mkdir, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';

const IMAGES_DIR  = new URL('../public/images/', import.meta.url).pathname;
const THUMBS_DIR  = new URL('../public/thumbs/', import.meta.url).pathname;
const SIZE        = 100;
const QUALITY     = 60;
const CONCURRENCY = 8;   // parallel workers — tune to your CPU/disk

async function needsRebuild(srcPath, destPath) {
  if (!existsSync(destPath)) return true;
  const [srcStat, destStat] = await Promise.all([stat(srcPath), stat(destPath)]);
  return srcStat.mtimeMs > destStat.mtimeMs;
}

async function processImage(file) {
  const srcPath  = path.join(IMAGES_DIR, file);
  const baseName = path.parse(file).name;          // e.g. "100050"
  const destPath = path.join(THUMBS_DIR, `${baseName}.webp`);

  if (!(await needsRebuild(srcPath, destPath))) return 'skipped';

  await sharp(srcPath)
    .resize(SIZE, SIZE, {
      fit: 'cover',
      position: 'centre',
    })
    .sharpen({ sigma: 0.3 })
    .webp({
      quality: QUALITY,
      smartSubsample: false,  // 4:2:0 chroma subsampling
      effort: 6,              // max compression effort (slower, smaller files)
    })
    // withMetadata() is intentionally omitted — Sharp strips EXIF/XMP by default
    .toFile(destPath);

  return 'created';
}

async function run() {
  await mkdir(THUMBS_DIR, { recursive: true });

  const files = (await readdir(IMAGES_DIR)).filter(f =>
    /\.(jpe?g|png|gif|webp|avif|tiff?)$/i.test(f)
  );

  console.log(`Found ${files.length} images. Processing with concurrency=${CONCURRENCY}…\n`);

  let created = 0, skipped = 0, failed = 0;
  const errors = [];

  // Process in batches of CONCURRENCY
  for (let i = 0; i < files.length; i += CONCURRENCY) {
    const batch = files.slice(i, i + CONCURRENCY);
    const results = await Promise.allSettled(batch.map(processImage));

    for (let j = 0; j < results.length; j++) {
      const r = results[j];
      if (r.status === 'fulfilled') {
        r.value === 'skipped' ? skipped++ : created++;
      } else {
        failed++;
        errors.push({ file: batch[j], reason: r.reason?.message ?? r.reason });
      }
    }

    // Progress line (overwrites in place)
    const done  = Math.min(i + CONCURRENCY, files.length);
    const pct   = ((done / files.length) * 100).toFixed(1);
    process.stdout.write(`\r  ${done}/${files.length} (${pct}%)  created=${created}  skipped=${skipped}  failed=${failed}   `);
  }

  console.log('\n\nDone.');
  console.log(`  Created : ${created}`);
  console.log(`  Skipped : ${skipped}  (already up-to-date)`);
  console.log(`  Failed  : ${failed}`);

  if (errors.length > 0) {
    console.error('\nErrors:');
    for (const { file, reason } of errors) {
      console.error(`  ${file}: ${reason}`);
    }
    process.exitCode = 1;
  }
}

run().catch(err => {
  console.error(err);
  process.exit(1);
});
