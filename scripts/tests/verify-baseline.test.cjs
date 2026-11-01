const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')
const { spawnSync } = require('node:child_process')
const { verifyBaseline, hashFile } = require('../verify-baseline.cjs')

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'investment-baseline-test-'))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  const write = (name, value) => {
    const filename = path.join(root, name)
    fs.mkdirSync(path.dirname(filename), { recursive: true })
    fs.writeFileSync(filename, value)
  }
  write('backend/main.py', 'app = 1\r\n')
  write('backend/pages/chat.py', 'deployed = 1\nlocal_context = True\n')
  write('deploy/backend-snapshot/pages/chat.py', 'deployed = 1\n')
  write('deploy/site-snapshot/index.html', '<script src="/assets/app.js"></script>\n')
  write('deploy/site-snapshot/assets/app.js', 'app()\n')
  const hash = (name) => hashFile(path.join(root, name))
  const manifest = {
    schemaVersion: 2, hashNormalization: 'utf8-text-crlf-to-lf',
    backendFiles: [
      { path: 'main.py', sha256: hash('backend/main.py'), serverRawSha256: 'a'.repeat(64), localComparison: 'identical' },
      { path: 'pages/chat.py', sha256: hash('deploy/backend-snapshot/pages/chat.py'), serverRawSha256: 'b'.repeat(64),
        repositorySha256: hash('backend/pages/chat.py'), snapshotPath: 'pages/chat.py',
        localComparison: 'intentional-difference', reason: 'Repository includes local context route.' }
    ],
    webFiles: ['index.html', 'assets/app.js'].map((name) => ({ path: name, sha256: hash(`deploy/site-snapshot/${name}`) }))
  }
  const save = () => write('docs/server-baseline.json', JSON.stringify(manifest))
  save()
  return { root, manifest, write, save }
}

test('checks both deployed and repository variants and normalizes checkout line endings', (t) => {
  const f = fixture(t)
  f.write('backend/main.py', 'app = 1\n')
  assert.deepEqual(verifyBaseline(f.root), { checked: 5, identicalBackend: 1, intentionalDifferences: 1, webFiles: 2 })
})

test('rejects an unexpected change to the repository-specific implementation', (t) => {
  const f = fixture(t)
  f.write('backend/pages/chat.py', 'deployed = 1\n')
  assert.throws(() => verifyBaseline(f.root), /Server baseline mismatch/)
})

test('rejects an unexpected change to the deployed variant archive', (t) => {
  const f = fixture(t)
  f.write('deploy/backend-snapshot/pages/chat.py', 'deployed = 2\n')
  assert.throws(() => verifyBaseline(f.root), /Server baseline mismatch/)
})

test('requires a reason for intentional repository/deployment differences', (t) => {
  const f = fixture(t)
  delete f.manifest.backendFiles[1].reason
  f.save()
  assert.throws(() => verifyBaseline(f.root), /Incomplete intentional difference/)
})

test('rejects leftover web bundles outside the manifest', (t) => {
  const f = fixture(t)
  f.write('deploy/site-snapshot/assets/old.js', 'old()\n')
  assert.throws(() => verifyBaseline(f.root), /file set differs/)
})

test('rejects a recorded web resource not referenced by the current HTML', (t) => {
  const f = fixture(t)
  f.write('deploy/site-snapshot/index.html', '<html></html>\n')
  f.manifest.webFiles[0].sha256 = hashFile(path.join(f.root, 'deploy/site-snapshot/index.html'))
  f.save()
  assert.throws(() => verifyBaseline(f.root), /exactly the files referenced/)
})

function historicalRepository(f) {
  const repositoryRoot = path.join(f.root, 'historical-source')
  fs.cpSync(path.join(f.root, 'backend'), path.join(repositoryRoot, 'backend'), { recursive: true })
  return repositoryRoot
}

test('an explicit historical source tree permits current implementation changes without relaxing the default check', (t) => {
  const f = fixture(t)
  const repositoryRoot = historicalRepository(f)
  f.write('backend/main.py', 'app = 2\n')
  f.write('backend/pages/chat.py', 'current_implementation = True\n')
  assert.throws(() => verifyBaseline(f.root), /Server baseline mismatch/)
  assert.deepEqual(verifyBaseline(f.root, { repositoryRoot }), {
    checked: 5, identicalBackend: 1, intentionalDifferences: 1, webFiles: 2,
  })
})

test('rejects modifications in the selected historical source tree', (t) => {
  const f = fixture(t)
  const repositoryRoot = historicalRepository(f)
  fs.writeFileSync(path.join(repositoryRoot, 'backend/main.py'), 'app = 9\n')
  assert.throws(() => verifyBaseline(f.root, { repositoryRoot }), /Server baseline mismatch/)
})

test('historical source selection still validates the current captured backend archive', (t) => {
  const f = fixture(t)
  const repositoryRoot = historicalRepository(f)
  f.write('deploy/backend-snapshot/pages/chat.py', 'tampered_archive = True\n')
  assert.throws(() => verifyBaseline(f.root, { repositoryRoot }), /Server baseline mismatch/)
})

test('historical source selection still validates the current captured web archive', (t) => {
  const f = fixture(t)
  const repositoryRoot = historicalRepository(f)
  f.write('deploy/site-snapshot/assets/app.js', 'tamperedArchive()\n')
  assert.throws(() => verifyBaseline(f.root, { repositoryRoot }), /Server baseline mismatch/)
})

test('CLI rejects unknown options and missing historical source paths before verification', () => {
  const script = path.join(__dirname, '..', 'verify-baseline.cjs')
  for (const [args, expected] of [
    [['--ignore-mismatch'], /Unknown or repeated argument/],
    [['--repository-root'], /--repository-root requires a path/],
    [['--repository-root', '--unknown'], /--repository-root requires a path/],
    [['--repository-root', '.', '--repository-root', '.'], /Unknown or repeated argument/],
  ]) {
    const result = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' })
    assert.notEqual(result.status, 0)
    assert.match(result.stderr, expected)
    assert.doesNotMatch(result.stderr, /Server baseline mismatch/)
  }
})
