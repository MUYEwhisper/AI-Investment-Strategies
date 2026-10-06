const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { readWindowState } = require('../window-state.cjs')
const displays = [{ workArea: { x: 0, y: 0, width: 1920, height: 1080 } }]

test('unplugging a monitor or corrupting saved state still leaves a usable window', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-invest-window-'))
  const filename = path.join(directory, 'state.json')
  try {
    assert.equal(readWindowState(filename, displays).width, 1440)
    fs.writeFileSync(filename, '{broken')
    assert.equal(readWindowState(filename, displays).width, 1440)
    fs.writeFileSync(filename, JSON.stringify({ x: 2500, y: 0, width: 1000, height: 700 }))
    assert.equal(readWindowState(filename, displays).x, undefined)
    fs.writeFileSync(filename, JSON.stringify({ x: 40, y: 40, width: 3000, height: 1400, maximized: true }))
    assert.deepEqual(readWindowState(filename, displays), { x: 40, y: 40, width: 1920, height: 1080, maximized: true })
  } finally {
    fs.rmSync(directory, { recursive: true })
  }
})
