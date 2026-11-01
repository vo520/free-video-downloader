/**
 * 前端样式契约回归验证（无需测试框架，node 直接运行）。
 *
 * 覆盖本轮重构建立的样式约定，防止回退：
 *  1. Tailwind v4 的 important 修饰符必须写成后缀式（flex! / sm:inline-flex!）。
 *     v3 的前缀式（!flex / !sm:inline-flex）在 v4 里与 variant 组合时会被整体丢弃，
 *     规则根本不生成 → 按钮该显示时不显示、hover 才出现的按钮永远不出现。
 *  2. z-index 只能用语义层级 token（z-dropdown / z-drawer / z-modal / z-toast / z-float），
 *     不允许再出现 z-[200] 这类魔法数字。
 *  3. 语义色必须来自 design token（bg-success-bg / text-error-text / bg-surface-muted 等），
 *     不允许再硬编码 bg-gray-100 / text-red-500 / hex 颜色。
 *
 * 运行：node test-style-contract.mjs
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.dirname(fileURLToPath(import.meta.url))
const SRC = path.join(ROOT, 'src')

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, out)
    else if (/\.(vue|js)$/.test(entry.name)) out.push(full)
  }
  return out
}

const files = walk(SRC)
const rel = (f) => path.relative(ROOT, f)

// ---- 抽取 class="..." / :class="..." 里的类词元 ----
const STATIC_ATTR = /(?<!:)\bclass="([^"]*)"/g
const BIND_ATTR = /:class="([^"]*)"/g
const STR_LIT = /'([^']*)'|"([^"]*)"/g

function classTokens(source) {
  const tokens = []
  for (const m of source.matchAll(STATIC_ATTR)) {
    tokens.push(...m[1].split(/\s+/).filter(Boolean))
  }
  for (const m of source.matchAll(BIND_ATTR)) {
    for (const lit of m[1].matchAll(STR_LIT)) {
      tokens.push(...(lit[1] ?? lit[2] ?? '').split(/\s+/).filter(Boolean))
    }
  }
  return tokens
}

// ---- 1. v3 前缀式 important ----
const V3_PREFIX = /^!|^[^ ]*!?:!/
const badImportant = []
for (const file of files) {
  for (const token of classTokens(fs.readFileSync(file, 'utf8'))) {
    if (!token.includes('!')) continue
    // 合法：结尾是 !（v4 后缀式）；非法：! 出现在开头或 variant 之后
    if (!token.endsWith('!')) badImportant.push(`${rel(file)}: ${token}`)
  }
}
assert.equal(
  badImportant.length,
  0,
  `发现 ${badImportant.length} 处 v3 前缀式 important（Tailwind v4 会丢弃与 variant 组合的这类规则）：\n  ${badImportant.join('\n  ')}`
)

// ---- 2. z-index 魔法数字 ----
const MAGIC_Z = /\bz-\[\d+\]/
const badZ = []
for (const file of files) {
  const source = fs.readFileSync(file, 'utf8')
  for (const m of source.matchAll(/class="([^"]*)"/g)) {
    for (const token of m[1].split(/\s+/)) {
      if (MAGIC_Z.test(token)) badZ.push(`${rel(file)}: ${token}`)
    }
  }
}
assert.equal(badZ.length, 0, `发现 z-index 魔法数字（请改用 z-dropdown/z-drawer/z-modal/z-toast/z-float）：\n  ${badZ.join('\n  ')}`)

// ---- 3. 硬编码灰阶 / 原始色 ----
const HARDCODED = /\b(?:bg|text|border)-(?:gray|slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/
const badColors = []
for (const file of files) {
  const source = fs.readFileSync(file, 'utf8')
  for (const m of source.matchAll(/class="([^"]*)"/g)) {
    for (const token of m[1].split(/\s+/)) {
      if (HARDCODED.test(token)) badColors.push(`${rel(file)}: ${token}`)
    }
  }
}
assert.equal(badColors.length, 0, `发现硬编码颜色（请改用语义 token）：\n  ${badColors.join('\n  ')}`)

// ---- 4. 关键设计 token 必须存在 ----
const css = fs.readFileSync(path.join(SRC, 'style.css'), 'utf8')
for (const token of [
  '--color-success-bg', '--color-success-text',
  '--color-warning-bg', '--color-warning-text',
  '--color-error-bg', '--color-error-text',
  '--color-info-bg', '--color-info-text',
  '--color-surface-muted', '--color-ring',
  '--z-dropdown', '--z-drawer', '--z-modal', '--z-toast', '--z-float',
]) {
  assert.ok(css.includes(token), `style.css 缺少设计 token：${token}`)
}
assert.ok(css.includes('prefers-reduced-motion'), 'style.css 缺少 prefers-reduced-motion 降级')
assert.ok(css.includes(':focus-visible'), 'style.css 缺少全局 focus-visible 焦点环')

console.log('样式契约回归验证全部通过')
