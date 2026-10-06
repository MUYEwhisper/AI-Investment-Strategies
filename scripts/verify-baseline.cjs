const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const root = path.resolve(__dirname, '..')
const baseline = JSON.parse(fs.readFileSync(path.join(root, 'docs/server-baseline.json'), 'utf8'))
let checked = 0
for (const [directory, files] of [['backend', baseline.backendFiles], ['deploy/site-snapshot', baseline.webFiles]]) {
  for (const entry of files) {
    const filename = path.join(root, directory, entry.path)
    const hash = crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex')
    if (hash !== entry.sha256) throw new Error(`Server baseline mismatch: ${directory}/${entry.path}`)
    checked++
  }
}
console.log(`Verified ${checked} production files (SHA-256).`)
if (!baseline.frontendBuildByteIdentical) {
  console.log('Note: the server build snapshot is authoritative; local source may produce a different hashed bundle.')
}
