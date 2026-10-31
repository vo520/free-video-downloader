/**
 * 前端 SSE 解析回归验证（无需测试框架，node 直接运行）。
 *
 * 背景：sse_starlette 的帧分隔符是 \r\n，而前端解析器原先只按 \n 切分，
 * 导致事件名带上 \r（callbacks['done\r'] 查不到）且空行分隔符变成 "\r"
 * （dispatch 永不触发）→ AI 总结/问答的所有回调全部失效。
 *
 * 本脚本用真实帧字节验证前端 api/summarize.js 的解析逻辑，
 * 同时覆盖 find 谓词（useHistory.removeHistory 按 id/url 双匹配）。
 *
 * 运行：node test-sse-parse.mjs
 */
import assert from 'node:assert/strict'

// ---- 复刻 frontend/src/api/summarize.js 的 handleSSEStream 解析逻辑 ----
function parseSSE(buffer, isFinal) {
  const events = []
  let currentEvent = ''
  let dataLines = []
  let hasData = false

  function dispatch() {
    if (hasData && currentEvent) {
      events.push({ event: currentEvent, data: dataLines.join('\n') })
    }
    dataLines = []
    hasData = false
    currentEvent = ''
  }

  let pending = ''
  if (buffer.endsWith('\r')) {
    pending = '\r'
    buffer = buffer.slice(0, -1)
  }
  const lines = buffer.split(/\r\n|\r|\n/)
  buffer = (lines.pop() || '') + pending

  for (const line of lines) {
    if (line === '') {
      dispatch()
      continue
    }
    if (line.startsWith(':')) continue
    const colonIdx = line.indexOf(':')
    if (colonIdx < 0) continue
    const field = line.slice(0, colonIdx)
    let val = line.slice(colonIdx + 1)
    if (val.startsWith(' ')) val = val.slice(1)
    if (field === 'event') {
      currentEvent = val
    } else if (field === 'data') {
      hasData = true
      dataLines.push(val)
    }
  }

  if (isFinal) dispatch()
  return { events, rest: buffer }
}

// ---- 真实 sse_starlette 帧字节 ----
const CRLF_FRAMES =
  'event: subtitle\r\ndata: {"has_subtitle":true}\r\n\r\n' +
  'event: summary\r\ndata: "这是总结"\r\n\r\n' +
  'event: done\r\ndata: [DONE]\r\n\r\n'

// ---- 旧解析器（仅按 \n 切分），用于确认原 bug ----
function parseSSEOld(buffer) {
  const events = []
  let currentEvent = ''
  let dataLines = []
  let hasData = false
  function dispatch() {
    if (hasData && currentEvent) events.push({ event: currentEvent, data: dataLines.join('\n') })
    dataLines = []
    hasData = false
    currentEvent = ''
  }
  const lines = buffer.split('\n')
  for (const line of lines) {
    if (line === '') { dispatch(); continue }
    if (line.startsWith(':')) continue
    const colonIdx = line.indexOf(':')
    if (colonIdx < 0) continue
    const field = line.slice(0, colonIdx)
    let val = line.slice(colonIdx + 1)
    if (val.startsWith(' ')) val = val.slice(1)
    if (field === 'event') currentEvent = val
    else if (field === 'data') { hasData = true; dataLines.push(val) }
  }
  return events
}

const old = parseSSEOld(CRLF_FRAMES)
// 旧解析器只会在最后触发一次 dispatch，且事件名带 \r：
// callbacks['done\r'] 查不到 → 所有回调都不触发（这正是原 bug）
assert.equal(old.length, 1, '旧解析器只能合并出最后一个事件')
assert.equal(old[0].event, 'done\r', '旧解析器事件名应带 \\r，查不到 done')
assert.ok(!old.some((e) => e.event === 'done'), '旧解析器不应产出可用的 done 事件')
assert.ok(!old.some((e) => e.event === 'summary'), '旧解析器不应产出可用的 summary 事件')

// ---- 新解析器：CRLF 帧 ----
const { events } = parseSSE(CRLF_FRAMES, true)
assert.equal(events.length, 3, `应解析出 3 个事件，实际 ${events.length}`)
assert.deepEqual(
  events.map((e) => e.event),
  ['subtitle', 'summary', 'done']
)
assert.equal(events[0].data, '{"has_subtitle":true}')
assert.equal(events[1].data, '"这是总结"')
assert.equal(events[2].data, '[DONE]')

// ---- LF 帧（其它 SSE 实现）仍要正常 ----
const lfFrames =
  'event: subtitle\ndata: {"has_subtitle":true}\n\n' +
  'event: done\ndata: [DONE]\n\n'
const lf = parseSSE(lfFrames, true)
assert.equal(lf.events.length, 2)
assert.deepEqual(lf.events.map((e) => e.event), ['subtitle', 'done'])

// ---- 分片到达：chunk 边界落在 \r\n 中间也不能错 ----
const chunkA = 'event: subtitle\r\ndata: {"a":1}\r\n\r\nevent: sum'
const chunkB = 'mary\r\ndata: "x"\r\n\r\nevent: done\r\ndata: [DONE]\r\n\r\n'
let acc = ''
acc += chunkA
const r1 = parseSSE(acc, false)
acc = r1.rest + chunkB
const r2 = parseSSE(acc, true)
assert.deepEqual(r1.events.map((e) => e.event), ['subtitle'])
assert.deepEqual(r2.events.map((e) => e.event), ['summary', 'done'])
assert.equal(r2.events[0].data, '"x"')

// ---- 复刻 useHistory.removeHistory 的 find 谓词 ----
function findHistoryItem(history, urlOrId) {
  return history.find(
    (h) =>
      (h.id != null && String(h.id) === String(urlOrId)) ||
      (h.url != null && h.url === urlOrId)
  )
}

const history = [
  { id: 101, url: 'https://www.douyin.com/video/7001' },
  { id: 102, url: 'https://www.bilibili.com/video/BV1xx' },
]
// 落地页删除传 item.url，顶栏删除传 item.id，两条路径都要能匹配到
assert.ok(findHistoryItem(history, 'https://www.douyin.com/video/7001'), '按 url 应能匹配')
assert.ok(findHistoryItem(history, 101), '按 id 应能匹配')
assert.ok(findHistoryItem(history, '101'), '按字符串 id 应能匹配')
assert.equal(findHistoryItem(history, 'https://none.test/v'), undefined)

console.log('SSE 解析与历史匹配回归验证全部通过')
