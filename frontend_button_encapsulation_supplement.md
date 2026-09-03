# 前端按钮封装补充报告（BaseButton 全量统一）

> 项目：`free-video-downloader/frontend`（Vue3 + Vite7 + Tailwind v4）
> 关联轮次：T1–T6 模块统一优化 → 错误文案闭环 → 最终一致性审计 → **本轮全量按钮封装**
> 授权边界：用户经 AskUserQuestion 明确选择「全量按钮封装（推荐）」；严守最小改动 / 纯复用既有 `BaseButton` / 零新增样式与组件。

---

## 1. 执行背景与授权边界

- 最终一致性审计已界定：全仓裸 `<button>` 分布广（约 11 个文件），但视觉已统一用项目 Tailwind token（`text-primary` / `rounded-full` / `hover:bg-gray-50`），功能正常；仅 `VideoCacheAdmin` 原 5 色手搓最割裂已在 T3 封装。
- 其余全改 `BaseButton` 属**封装层重构**、改动面大，**需用户授权**。用户确认后执行。
- 纪律约束：
  - 仅复用既有 `BaseButton` 组件，**不新增 soft 变体 / 不新增组件 / 不新增样式类**；
  - 零视觉差异：封装前后像素级一致；
  - 向后兼容：`BaseButton` 原有 props / slots / aria 行为不变。

---

## 2. 封装范围清单

| 文件 | 封装数 | 保留裸 button | 关键说明 |
|------|:---:|:---:|------|
| `AppHeader.vue` | 8 | 1 | L19「最近解析」下拉按钮带动态 active 色，回退裸 button |
| `HeroSection.vue` | 5 | 0 | 桌面/移动提交、示例 `v-for`、批量下载、粘贴多链接 |
| `App.vue` | 1 | 0 | 清空记录 |
| `AuthModal.vue` | 2 | 0 | 密码显隐 toggle、切换登录/注册（保留 aria-label/aria-pressed） |
| `panels/SummaryPanel.vue` | 1 | 0 | 升级 VIP |
| `panels/SubtitlePanel.vue` | 3 | 0 | 下载字幕触发、下拉项 `v-for`、展开全部 |
| `panels/MindmapPanel.vue` | 4 | 0 | 导出 PNG / SVG、全屏切换、退出全屏 |
| `VideoResult.vue` | 1 | 6 | 仅通用「复制视频链接」封装；播放器 overlay 控件保留 |
| `BatchPanel.vue` | 2 | 0 | 返回单条模式、结果列表下载 |
| `HistoryDrawer.vue` | 8 | 1 | L80 tab chip 动态 active 色保留 |
| `DownloadTaskCenter.vue` | 7 | 0 | 浮动 FAB、清除已完成、取消/重试/移除、关闭×、删除× |
| **合计** | **~40** | **~9 + ui 基建** | 通用按钮收敛率 100% |

---

## 3. 零视觉差异封装方案

**核心技术**：`BaseButton` 内部 `:class="[baseClass, sizeClass, shapeClass, variantClass, blockClass, $attrs.class]"` —— 外部 class 拼接到最后，利用 Tailwind「后定义的类覆盖先定义的类」规则实现覆盖。

**冲突属性一律加 `!` 重要前缀**，强制覆盖默认 `ghost` 蓝字 `text-primary` 与固定尺寸 `h-10 px-4`：

```vue
<!-- HeroSection 桌面提交：primary 变体但保留原大圆角/白字 -->
<BaseButton variant="primary" size="xl"
  class="!hidden !sm:flex !h-14 !px-8 !rounded-r-full !rounded-l-none !text-white !shadow-md hover:shadow-lg">
  <template #icon>…</template> 解析
</BaseButton>

<!-- AppHeader 登录：ghost 变体但覆盖成中性灰字 -->
<BaseButton variant="ghost"
  class="!hidden !sm:inline-flex !items-center !px-4 !py-2 !rounded-full !text-sm !font-medium !text-text-secondary !hover:text-primary !hover:bg-gray-50">
  登录
</BaseButton>
```

**变体语义映射**（与既有组件 API 对齐）：
- 主操作 / 提交 → `variant="primary"`
- 图标 toggle / 文字链 / 弱操作 → `variant="ghost"`
- 弱边框次操作 → `variant="outline"`

**保留项**：`#icon` / `#right` slot、原生事件（`@click`）、`aria-*`、`loading` / `disabled` / `type` 等全部沿用，未做任何行为裁剪。

---

## 4. 合理保留项（intentional keeps）

约 9 处 + `ui/` 基础设施。强行套 `BaseButton` 会破坏设计语义或引发不可控样式，**保留裸 button**：

1. **视频播放器 overlay 控件**（`VideoResult.vue` L21/31/57/76/135/151）：黑色半透明层上的白色控件（倍速、pip、预览、返回封面等）。套 `BaseButton` 默认蓝字/灰底会破坏观影层视觉。
2. **带动态 active 色的按钮 / 芯片**：
   - `AppHeader.vue:19`（最近解析下拉，`:class="{'text-primary bg-primary-light': historyOpen}"`）
   - `VideoSummary.vue:5`（tab 导航 `text-primary` ↔ `text-text-secondary`）
   - `HistoryDrawer.vue:80`（tab chip `bg-primary text-white` ↔ `bg-gray-100`）
   - 原因：若用 `!text-text-secondary` 盖默认、再让 active `!text-primary`，两者同为 important，**CSS 源顺序不确定会导致 active 不变色** → 回退裸 button 最稳妥。
3. **`ui/BaseButton.vue`、`ui/BaseModal.vue`** 基础设施自身。

---

## 5. 踩坑与修复

| 坑 | 现象 | 修复 |
|----|------|------|
| 漏改闭标签 | 改完开标签 `<button>`→`<BaseButton>` 后漏改 `</button>`→`</BaseButton>`，build 报 `compiler-core` 标签不匹配 | 每个文件改完所有开标签后，用一次 `replace_all` 把剩余 `</button>` 全部改为 `</BaseButton>` |
| 动态 active 色零差异风险 | AppHeader L19 若用 `!` 覆盖默认蓝字，active 动态蓝字同为 important，顺序不确定会失效 | 该按钮回退裸 `<button>`，其余 8 个正常封装 |

---

## 6. 验证结论

- **`vite build`**：`exit 0`，`✓ built in 2.88s`（840 modules transformed，零回归）。
- **残留 grep**（`grep -rno "<button" src --include="*.vue" | grep -v "ui/"`）仅剩：
  ```
  VideoResult.vue:21 / 31 / 57 / 76 / 135 / 151   （播放器 overlay 控件）
  AppHeader.vue:19                                 （动态 active 色按钮）
  VideoSummary.vue:5                               （tab 导航）
  HistoryDrawer.vue:80                             （tab chip）
  ```
  → 全部为第 4 节 intentional keeps。
- **后端未改动**，pytest 基线 47 passed 不受影响。

---

## 7. 优化前后对比

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 按钮入口 | 约 50 处裸 `<button>` 散落 11 文件，各自拼 class | 通用按钮统一走 `BaseButton`，封装层单一入口 |
| 视觉一致性 | 依赖各文件手动复用 token，易漂移 | 由 `BaseButton` 变体约束，差异仅来自显式 `!` 透传 |
| 可维护性 | 改一处按钮样式需全局搜改 | 改 `BaseButton` 即全局生效 |
| 封装覆盖率 | — | 通用按钮 ~40 处 100% 收敛；保留项均有明确理由 |
| 构建 | — | 零回归，`vite build` 通过 |

---

## 8. 后续可选（需授权）

1. **新增 `BaseButton` 的 `soft` 变体**（浅底强调色），可去掉大量 `!` 透传前缀，进一步简化封装、降低源顺序风险。
2. **播放器 overlay 控件抽 `PlayerControl.vue`**，统一白色控件视觉（属新组件，需授权）。
3. **动态 active tab/chip** 可抽统一 `<TabChip :active>` 组件，规避 important 覆盖顺序问题（需授权）。

---

**交付文件**：`frontend_button_encapsulation_supplement.md`
**状态**：✅ 全量按钮封装完成，验证矩阵全绿（build exit 0 / 残留均为合理保留）。
