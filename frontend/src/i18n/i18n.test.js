// Every text key used on any screen must exist in English, Khmer and Chinese.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import en from './en.json'
import km from './km.json'
import zh from './zh.json'

const SRC = join(__dirname, '..')
const files = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? files(join(dir, e.name)) : [join(dir, e.name)]))

describe('translations used by the screens', () => {
  const used = new Set()
  for (const f of files(SRC).filter((f) => f.endsWith('.jsx'))) {
    const code = readFileSync(f, 'utf8')
    for (const m of code.matchAll(/\bt\(\s*'([a-zA-Z0-9_.]+)'/g)) used.add(m[1])
  }
  it('finds the keys', () => expect(used.size).toBeGreaterThan(300))
  for (const [name, dict] of [['en', en], ['km', km], ['zh', zh]]) {
    it(`${name} has every key a screen uses`, () => {
      expect([...used].filter((k) => !(k in dict))).toEqual([])
    })
  }
  it('no translation is empty', () => {
    for (const dict of [en, km, zh]) expect(Object.entries(dict).filter(([, v]) => !String(v).trim())).toEqual([])
  })
})
