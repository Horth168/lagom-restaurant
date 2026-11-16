// Telegram profile photos (shown as circles, so everything sits in the safe middle area).
// Run from the project folder:  node brand/make_telegram_photos.mjs
// Writes brand/telegram/lagom-bot.png and brand/telegram/lagom-payments-group.png (1024 × 1024).
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const here = dirname(fileURLToPath(import.meta.url))
const require = createRequire(join(here, '..', 'frontend', 'package.json'))
const sharp = require('sharp')

const FOREST = '#263D31'
const CREAM = '#F3EBDD'
const GOLD = '#C58B50'
const S = 1024

// The wordmark's letter strokes, recoloured
const wordmark = (colour) =>
  readFileSync(join(here, 'lagom-wordmark.svg'), 'utf8')
    .replace(/^<svg[^>]*>/, '')
    .replace(/<\/svg>\s*$/, '')
    .replaceAll('#263D31', colour)

// Mark (ring + gold half-moon) centred at (cx, cy) with outer radius r
const mark = (cx, cy, r, ring) => {
  const stroke = r * 0.154
  const inner = r * 0.769
  return `
    <defs><clipPath id="half"><circle cx="${cx}" cy="${cy}" r="${inner}"/></clipPath></defs>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${ring}" stroke-width="${stroke}"/>
    <rect x="${cx - r}" y="${cy + stroke}" width="${2 * r}" height="${r}" fill="${GOLD}" clip-path="url(#half)"/>`
}

function photo({ bg, ink, label }) {
  const wmW = 440 // wordmark width
  const wmH = (wmW / 228) * 44
  const markR = 170
  // centre the whole group (mark + name + label) vertically, so it sits in the middle of the circle
  const height = 2 * markR + 70 + wmH + (label ? 80 : 0)
  const top = (S - height) / 2 + markR // centre of the mark
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${S} ${S}">
    <rect width="${S}" height="${S}" fill="${bg}"/>
    ${mark(S / 2, top, markR, ink)}
    <svg x="${(S - wmW) / 2}" y="${top + markR + 70}" width="${wmW}" height="${wmH}" viewBox="0 0 228 44">${wordmark(ink)}</svg>
    ${label ? `<text x="${S / 2}" y="${top + markR + 70 + wmH + 80}" text-anchor="middle"
      font-family="Inter, Arial, Helvetica, sans-serif" font-size="46" font-weight="700" letter-spacing="14" fill="${GOLD}">${label}</text>` : ''}
  </svg>`
}

const out = join(here, 'telegram')
mkdirSync(out, { recursive: true })
const files = {
  'lagom-bot.png': photo({ bg: FOREST, ink: CREAM }),
  'lagom-payments-group.png': photo({ bg: CREAM, ink: FOREST, label: 'PAYMENTS' }),
}
for (const [name, svg] of Object.entries(files)) {
  writeFileSync(join(out, name.replace('.png', '.svg')), svg)
  await sharp(Buffer.from(svg)).png().toFile(join(out, name))
  console.log('wrote', join('brand', 'telegram', name))
}
