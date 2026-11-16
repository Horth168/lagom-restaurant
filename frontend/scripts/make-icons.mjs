// Builds PNG app icons and copies brand SVGs into public/. Run: npm run icons
import sharp from 'sharp'
import { copyFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const p = (rel) => fileURLToPath(new URL(rel, import.meta.url))
mkdirSync(p('../public/icons/'), { recursive: true })

const sizes = [
  ['icons/icon-192.png', 192],
  ['icons/icon-512.png', 512],
  ['icons/maskable-512.png', 512],
  ['icons/apple-touch-icon.png', 180],
]
for (const [name, size] of sizes) {
  await sharp(p('../../brand/app-icon.svg'), { density: 300 }).resize(size, size).png().toFile(p(`../public/${name}`))
}
for (const f of ['favicon.svg', 'lagom-mark.svg', 'lagom-logo-horizontal.svg', 'lagom-logo-horizontal-reversed.svg']) {
  copyFileSync(p(`../../brand/${f}`), p(`../public/${f}`))
}
console.log('Icons written to public/icons')
