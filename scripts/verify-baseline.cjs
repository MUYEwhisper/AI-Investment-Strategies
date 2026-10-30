const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const textExtensions = new Set(['.py', '.md', '.html', '.css', '.js', '.json', '.ts', '.vue', '.txt'])
const sha256Pattern = /^[0-9a-f]{64}$/

// Git may change checkout line endings. The manifest compares UTF-8 text with
// CRLF normalized to LF; serverRawSha256 separately records captured bytes.
function hashFile(filename) {
  let contents = fs.readFileSync(filename)
  if (textExtensions.has(path.extname(filename).toLowerCase())) {
    contents = Buffer.from(contents.toString('utf8').replace(/\r\n/g, '\n'), 'utf8')
  }
  return crypto.createHash('sha256').update(contents).digest('hex')
}
function resolveInside(directory, relativePath) {
  if (typeof relativePath !== 'string' || !relativePath || path.isAbsolute(relativePath)) {
    throw new Error(`Invalid baseline path: ${relativePath}`)
  }
  const filename = path.resolve(directory, relativePath)
  const relative = path.relative(directory, filename)
  if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error(`Invalid baseline path: ${relativePath}`)
  return filename
}

function verifyHash(filename, expected) {
  if (!sha256Pattern.test(expected || '')) throw new Error(`Invalid SHA-256: ${filename}`)
  if (hashFile(filename) !== expected) throw new Error(`Server baseline mismatch: ${filename}`)
}

function listFiles(directory, prefix = '') {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const name = prefix + entry.name
    return entry.isDirectory() ? listFiles(path.join(directory, entry.name), `${name}/`) : [name]
  })
}

function verifyBaseline(root) {
  const baseline = JSON.parse(fs.readFileSync(path.join(root, 'docs/server-baseline.json'), 'utf8'))
  if (baseline.schemaVersion !== 2 || baseline.hashNormalization !== 'utf8-text-crlf-to-lf') {
    throw new Error('Unsupported server baseline schema or hash normalization')
  }
  let checked = 0
  let identicalBackend = 0
  let intentionalDifferences = 0
  for (const entry of baseline.backendFiles) {
    if (!sha256Pattern.test(entry.serverRawSha256 || '')) throw new Error(`Missing captured raw hash: ${entry.path}`)
    const repositoryFile = resolveInside(path.join(root, 'backend'), entry.path)
    if (entry.localComparison === 'identical') {
      if (entry.repositorySha256 || entry.snapshotPath) throw new Error(`Unexplained baseline metadata: ${entry.path}`)
      verifyHash(repositoryFile, entry.sha256)
      identicalBackend++
    } else if (entry.localComparison === 'intentional-difference') {
      if (!entry.reason || !entry.snapshotPath || entry.repositorySha256 === entry.sha256) {
        throw new Error(`Incomplete intentional difference: ${entry.path}`)
      }
      verifyHash(repositoryFile, entry.repositorySha256)
      verifyHash(resolveInside(path.join(root, 'deploy/backend-snapshot'), entry.snapshotPath), entry.sha256)
      intentionalDifferences++
      checked++
    } else {
      throw new Error(`Unrecognized backend comparison: ${entry.path}`)
    }
    checked++
  }
  const webDirectory = path.join(root, 'deploy/site-snapshot')
  for (const entry of baseline.webFiles) {
    verifyHash(resolveInside(webDirectory, entry.path), entry.sha256)
    checked++
  }
  const recordedWeb = baseline.webFiles.map((entry) => entry.path).sort()
  if (JSON.stringify(recordedWeb) !== JSON.stringify(listFiles(webDirectory).sort())) {
    throw new Error('Web snapshot file set differs from the manifest')
  }
  const html = fs.readFileSync(path.join(webDirectory, 'index.html'), 'utf8')
  const referencedWeb = new Set(['index.html'])
  for (const match of html.matchAll(/(?:src|href)=["']\/([^"'#?]+)(?:[?#][^"']*)?["']/g)) {
    referencedWeb.add(match[1])
  }
  if (JSON.stringify(recordedWeb) !== JSON.stringify([...referencedWeb].sort())) {
    throw new Error('Web snapshot must contain exactly the files referenced by index.html')
  }
  return { checked, identicalBackend, intentionalDifferences, webFiles: baseline.webFiles.length }
}

if (require.main === module) {
  const result = verifyBaseline(path.resolve(__dirname, '..'))
  console.log(`Verified ${result.checked} local baseline artifacts (SHA-256, UTF-8 text normalized to LF).`)
  console.log(`Backend: ${result.identicalBackend} match the captured server source; ${result.intentionalDifferences} documented repository/deployment difference(s).`)
  console.log(`Web: ${result.webFiles} captured deployment files; this check does not contact production or prove a reproducible Vue build.`)
}

module.exports = { verifyBaseline, hashFile }
