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
// iPhone / iPad splash screens: cream background with the LAGOM mark (portrait)
mkdirSync(p('../public/splash/'), { recursive: true })
const SPLASH = [[750, 1334], [1170, 2532], [1179, 2556], [1284, 2778], [1290, 2796], [1640, 2360], [2048, 2732]]
for (const [w, h] of SPLASH) {
  const size = Math.round(Math.min(w, h) * 0.28)
  const mark = await sharp(p('../../brand/lagom-mark.svg'), { density: 400 }).resize(size, size).png().toBuffer()
  await sharp({ create: { width: w, height: h, channels: 3, background: '#F3EBDD' } })
    .composite([{ input: mark, left: Math.round((w - size) / 2), top: Math.round((h - size) / 2) - Math.round(h * 0.04) }])
    .png({ compressionLevel: 9 })
    .toFile(p(`../public/splash/splash-${w}x${h}.png`))
}

for (const f of ['favicon.svg', 'lagom-mark.svg', 'lagom-logo-horizontal.svg', 'lagom-logo-horizontal-reversed.svg']) {
  copyFileSync(p(`../../brand/${f}`), p(`../public/${f}`))
}
console.log('Icons written to public/icons')
