const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { JSDOM } = require('jsdom')

const source = fs.readFileSync(process.env.LOCAL_AI_TEST_SOURCE || path.join(__dirname, '..', 'local-ai.html'), 'utf8')
const inlineScript = source.match(/<script>([\s\S]*?)<\/script>/)[1]

function streamReply() {
  let controller
  const body = new ReadableStream({ start(value) { controller = value } })
  return {
    response: new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }),
    delta(text) { controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({ choices: [{ delta: { content: text } }] })}\n\n`)) },
    finish() { controller.enqueue(new TextEncoder().encode('data: [DONE]\n\n')); controller.close() },
  }
}

async function until(predicate, message) {
  for (let attempt = 0; attempt < 60; attempt++) {
    if (predicate()) return
    await new Promise(resolve => setImmediate(resolve))
  }
  assert.ok(predicate(), message)
}

async function fixture(t) {
  const dom = new JSDOM(source, { url: 'https://local-ai.test/local-ai.html', runScripts: 'outside-only', pretendToBeVisual: true })
  t.after(() => dom.window.close())
  const requests = []
  const replies = []
  let statusListener
  const window = dom.window
  window.TextDecoder = TextDecoder
  window.AbortSignal = AbortSignal
  window.aiInvestmentDesktop = {
    getLocalModelSettings: async () => ({ gpuAvailable: true, gpuEnabled: false, gpuActive: false }),
    getLocalModelStatus: async () => ({ installed: true, running: true }),
    onLocalModelStatus(callback) { statusListener = callback },
  }
  window.fetch = async (url, options) => {
    if (url.endsWith('/health')) return { ok: true, json: async () => ({ status: 'ok' }) }
    if (url.endsWith('/chat/local-context')) return { ok: true, json: async () => ({ records: [] }) }
    if (url.endsWith('/v1/chat/completions')) {
      requests.push(JSON.parse(options.body))
      assert.ok(replies.length, 'A programmed reply is required; no real network is allowed')
      return replies.shift()
    }
    throw new Error(`Unexpected fetch: ${url}`)
  }
  vm.runInContext(inlineScript, dom.getInternalVMContext())
  const $ = id => window.document.getElementById(id)
  await until(() => !$('input').disabled, 'Healthy startup must enable the composer')
  return {
    window, document: window.document, $, requests,
    reply(value) { replies.push(value) },
    status(value) { statusListener(value) },
    submit(prompt, keyboard = false) {
      $('input').value = prompt
      $('input').dispatchEvent(new window.Event('input', { bubbles: true }))
      if (keyboard) $('input').dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
      else $('send').click()
    },
    async finished(count) {
      await until(() => JSON.parse(window.localStorage.getItem('ai_invest_local_chats'))[0].messages.filter(message => message.role === 'assistant' && !message.pending).length === count + 1,
        'A completed reply must be persisted')
    },
  }
}

test('local assistant enables and focuses the composer after every reply across three questions', async t => {
  const f = await fixture(t)
  for (let index = 1; index <= 3; index++) {
    const reply = streamReply()
    f.reply(reply.response)
    f.$('input').focus()
    f.submit(`问题 ${index}`, index === 2)
    assert.equal(f.$('input').disabled, true)
    assert.equal(f.$('send').disabled, true)
    await until(() => f.requests.length === index, 'Each submission must reach the local completion endpoint once')
    reply.delta(`第 ${index} 个回答`)
    reply.finish()
    await f.finished(index)
    assert.equal(f.$('input').disabled, false, `Reply ${index} must unlock the input`)
    assert.equal(f.$('send').disabled, false, `Reply ${index} must unlock the send button`)
    assert.equal(f.document.activeElement, f.$('input'), `Reply ${index} must focus the enabled input`)
    assert.equal(f.$('gpuToggle').disabled, false)
    assert.equal(f.$('status').textContent, '本机模型就绪')
  }
  assert.deepEqual(f.requests[2].messages.filter(message => message.role === 'user').map(message => message.content), ['问题 1', '问题 2', '问题 3'])
  assert.match(f.requests[2].messages.filter(message => message.role === 'assistant').at(-1).content, /第 2 个回答/)
  assert.equal(f.document.querySelectorAll('.message.pending').length, 0)
})

test('local assistant cannot submit a duplicate while streaming, including model-ready notifications', async t => {
  const f = await fixture(t)
  const reply = streamReply()
  f.reply(reply.response)
  f.submit('第一轮')
  await until(() => f.requests.length === 1, 'First request must start')
  f.status({ installed: true, running: true })
  assert.equal(f.$('input').disabled, true)
  assert.equal(f.$('send').disabled, true)
  f.$('input').value = '不应并发发送'
  f.$('composer').dispatchEvent(new f.window.Event('submit', { bubbles: true, cancelable: true }))
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(f.requests.length, 1)
  assert.equal(f.document.querySelectorAll('.message.user').length, 1)
  reply.delta('已完成')
  reply.finish()
  await f.finished(1)
  assert.equal(f.$('input').disabled, false)
  assert.equal(f.$('send').disabled, false)
})

test('local assistant restores input after a failed request when the model becomes available again', async t => {
  const f = await fixture(t)
  f.reply({ ok: false, body: null })
  f.submit('失败请求')
  await until(() => f.$('error').textContent.includes('本地模型服务请求失败'), 'A failed request must show its error')
  assert.equal(f.document.querySelectorAll('.message.pending').length, 0)
  assert.equal(f.$('input').disabled, true, 'An unavailable model must keep submission disabled')
  assert.equal(f.$('setup').hidden, false)
  f.status({ installed: true, running: true })
  assert.equal(f.$('input').disabled, false)
  assert.equal(f.$('send').disabled, false)
  const reply = streamReply()
  f.reply(reply.response)
  f.submit('恢复后继续提问', true)
  await until(() => f.requests.length === 2, 'A new question must be accepted after model recovery')
  reply.delta('恢复后的回答')
  reply.finish()
  await f.finished(1)
  assert.equal(f.$('input').disabled, false)
  assert.equal(f.$('send').disabled, false)
  assert.equal(f.$('error').textContent, '')
})

test('local assistant keeps controls disabled for model-down status and enables them when it returns', async t => {
  const f = await fixture(t)
  f.status({ installed: true, running: false })
  assert.equal(f.$('input').disabled, true)
  assert.equal(f.$('send').disabled, true)
  f.$('input').value = '模型未运行时不要请求'
  f.$('composer').dispatchEvent(new f.window.Event('submit', { bubbles: true, cancelable: true }))
  assert.equal(f.requests.length, 0)
  f.status({ installed: true, running: true })
  assert.equal(f.$('input').disabled, false)
  assert.equal(f.$('send').disabled, false)
  const prevented = !f.$('input').dispatchEvent(new f.window.KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true, cancelable: true }))
  assert.equal(prevented, false, 'Shift+Enter must remain available for a newline')
  assert.equal(f.requests.length, 0)
})
