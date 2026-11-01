<template>
  <div class="video-cache-admin">
    <!-- 无权限状态：服务端对缓存后台的全部读/写接口要求管理员（ADMIN_EMAILS 白名单）。
         顶栏入口已对非管理员隐藏，这里再兜一层，避免出现「一片空白 + 通用报错」的困惑。 -->
    <EmptyState
      v-if="forbidden"
      variant="error"
      title="需要管理员权限"
      desc="视频缓存管理是运维级后台，仅对管理员开放。如需访问，请将你的邮箱加入后端的 ADMIN_EMAILS 白名单后重新登录。"
    />
    <template v-else>
    <!--
      分区切换：缓存条目 / 缓存规则 / 解析日志。
      此前后端已实现 cache_rules 与 parse_logs 的完整 CRUD，
      但前端没有任何入口 —— 表恒空、接口无 UI，等于两套能力凭空闲置。
    -->
    <div class="flex gap-1 p-1 bg-surface-muted rounded-xl mb-6 w-fit max-w-full overflow-x-auto" role="tablist" aria-label="缓存管理分区">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        role="tab"
        :aria-selected="activeTab === tab.key"
        class="px-4 h-9 text-sm font-medium rounded-lg transition-all whitespace-nowrap"
        :class="activeTab === tab.key
          ? 'bg-white text-text-primary shadow-sm'
          : 'text-text-secondary hover:text-text-primary'"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- ===== 缓存条目 ===== -->
    <template v-if="activeTab === 'videos'">
    <!-- 头部统计卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-xl border border-border shadow-sm p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-text-muted">总缓存数</p>
            <p class="text-2xl font-bold text-text-primary">{{ stats.total_videos || 0 }}</p>
          </div>
          <div class="w-10 h-10 bg-primary-light rounded-full flex items-center justify-center">
            <svg class="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-border shadow-sm p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-text-muted">活跃缓存</p>
            <p class="text-2xl font-bold text-success">{{ stats.active_cache || 0 }}</p>
          </div>
          <div class="w-10 h-10 bg-success-bg rounded-full flex items-center justify-center">
            <svg class="w-5 h-5 text-success-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-border shadow-sm p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-text-muted">热门缓存</p>
            <p class="text-2xl font-bold text-warning-text">{{ stats.hot_cache || 0 }}</p>
          </div>
          <div class="w-10 h-10 bg-warning-bg rounded-full flex items-center justify-center">
            <svg class="w-5 h-5 text-warning-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-border shadow-sm p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-text-muted">总访问次数</p>
            <p class="text-2xl font-bold text-neutral-text">{{ stats.total_cache_hits || 0 }}</p>
          </div>
          <div class="w-10 h-10 bg-neutral-bg rounded-full flex items-center justify-center">
            <svg class="w-5 h-5 text-neutral-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- 筛选和操作栏 -->
    <div class="bg-white rounded-xl border border-border shadow-sm p-4 mb-6">
      <div class="flex flex-col md:flex-row gap-4">
        <!-- 搜索框 -->
        <div class="flex-1">
          <input
            v-model="filters.search"
            type="text"
            placeholder="搜索视频标题、URL或UP主..."
            class="w-full h-10 px-4 border border-border rounded-xl bg-white text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
            @keyup.enter="searchVideos"
          />
        </div>

        <!-- 平台筛选 -->
        <select
          v-model="filters.platform"
          class="h-10 px-4 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          @change="applyFilters"
        >
          <option value="">全部平台</option>
          <option value="youtube">YouTube</option>
          <option value="bilibili">哔哩哔哩</option>
          <option value="douyin">抖音</option>
          <option value="twitter">Twitter</option>
        </select>

        <!-- 状态筛选 -->
        <select
          v-model="filters.cacheStatus"
          class="h-10 px-4 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          @change="applyFilters"
        >
          <option value="">全部状态</option>
          <option value="active">活跃</option>
          <option value="expired">已过期</option>
        </select>

        <!-- 仅热门 -->
        <label class="flex items-center gap-2">
          <input
            v-model="filters.hotOnly"
            type="checkbox"
            class="w-4 h-4 text-primary border-border rounded focus:ring-primary/20"
            @change="applyFilters"
          />
          <span class="text-sm text-text-secondary">仅热门</span>
        </label>

        <!-- 操作按钮 -->
        <BaseButton variant="primary" size="md" shape="square" @click="searchVideos">搜索</BaseButton>
        <BaseButton variant="outline" size="md" shape="square" @click="showExportDialog = true">导出数据</BaseButton>
        <BaseButton
          variant="danger"
          size="md"
          shape="square"
          :disabled="cleaningUp"
          @click="cleanupExpired"
        >{{ cleaningUp ? '清理中…' : '清理过期' }}</BaseButton>
      </div>
    </div>

    <!-- 视频列表 -->
    <div class="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-border">
          <thead class="bg-surface-muted">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">视频信息</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">平台</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">时长/大小</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">缓存状态</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">访问统计</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-border">
            <tr v-if="loading">
              <td colspan="6">
                <EmptyState variant="loading" title="加载中…" />
              </td>
            </tr>
            <tr v-else-if="errorMsg">
              <td colspan="6">
                <EmptyState variant="error" :title="errorMsg">
                  <template #action>
                    <BaseButton variant="primary" size="sm" shape="square" @click="loadVideos">重试</BaseButton>
                  </template>
                </EmptyState>
              </td>
            </tr>
            <tr v-else-if="videos.length === 0">
              <td colspan="6">
                <EmptyState variant="empty" title="暂无缓存数据" desc="在首页解析视频后，结果会自动归档到这里。" />
              </td>
            </tr>
            <template v-else>
              <tr v-for="video in videos" :key="video.id" class="hover:bg-surface-muted">
                <td class="px-6 py-4">
                  <div class="flex items-center gap-3">
                    <VideoThumbnail :url="video.thumbnail_url" size="md" />
                    <div class="min-w-0">
                      <p class="text-sm font-medium text-text-primary truncate max-w-xs">{{ video.title || '无标题' }}</p>
                      <p class="text-xs text-text-muted truncate max-w-xs">{{ video.video_url }}</p>
                    </div>
                  </div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <span class="px-2 py-1 text-xs font-medium rounded-full" :class="getPlatformClass(video.platform)">
                    {{ video.platform || 'unknown' }}
                  </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-text-muted">
                  <div>{{ formatDuration(video.duration) }}</div>
                  <div>{{ formatFileSize(video.file_size) }}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <span
                    class="px-2 py-1 text-xs font-medium rounded-full"
                    :class="getStatusClass(video.cache_status)"
                  >
                    {{ video.cache_status || 'active' }}
                  </span>
                  <span v-if="video.is_hot" class="ml-2 px-2 py-1 text-xs font-medium bg-warning-bg text-warning-text rounded-full">
                    热门
                  </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-text-muted">
                  <div>访问 {{ video.cache_hit_count || 0 }} 次</div>
                  <div class="text-xs text-text-muted">{{ formatDate(video.last_access_at) }}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm">
                  <div class="flex flex-wrap gap-2">
                    <!-- 播放按钮 -->
                    <BaseButton
                      v-if="video.direct_url || (video.download_url && isPlayableUrl(video.download_url))"
                      variant="ghost"
                      size="xs"
                      shape="square"
                      @click="playVideo(video)"
                    >
                      播放
                    </BaseButton>
                    <!-- 下载按钮 -->
                    <BaseButton
                      v-if="video.download_url"
                      variant="ghost"
                      size="xs"
                      shape="square"
                      @click="downloadVideo(video)"
                    >
                      下载
                    </BaseButton>
                    <!-- 复制链接 -->
                    <BaseButton
                      v-if="video.download_url"
                      variant="ghost"
                      size="xs"
                      shape="square"
                      @click="copyUrl(video.download_url)"
                    >
                      复制
                    </BaseButton>
                    <!-- 标记为热门 -->
                    <BaseButton
                      variant="ghost"
                      size="xs"
                      shape="square"
                      :disabled="pendingActions.has(video.video_url)"
                      @click="markHot(video)"
                    >
                      {{ pendingActions.has(video.video_url) ? '处理中…' : '标热门' }}
                    </BaseButton>
                    <!-- 删除 -->
                    <BaseButton
                      variant="danger"
                      size="xs"
                      shape="square"
                      :disabled="pendingActions.has(video.video_url)"
                      @click="deleteVideo(video)"
                    >
                      删除
                    </BaseButton>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- 分页 -->
      <div class="px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-border-light">
        <div class="text-sm text-text-muted">
          显示 {{ videos.length }} 条，共 {{ total }} 条
        </div>
        <div class="flex gap-2">
          <BaseButton
            variant="outline"
            size="xs"
            shape="square"
            :disabled="currentPage === 1"
            @click="prevPage"
          >
            上一页
          </BaseButton>
          <BaseButton
            variant="outline"
            size="xs"
            shape="square"
            :disabled="loading || currentPage * pageSize >= total"
            @click="nextPage"
          >
            下一页
          </BaseButton>
        </div>
      </div>
    </div>
    </template>

    <!-- ===== 缓存规则 ===== -->
    <template v-else-if="activeTab === 'rules'">
      <div class="bg-info-bg border border-primary/20 rounded-xl p-4 mb-6 flex items-start gap-3">
        <svg class="w-5 h-5 text-info-text shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p class="text-sm text-info-text leading-relaxed">
          规则按 <strong>优先级从高到低</strong> 匹配，命中的第一条规则决定该视频的缓存时长（TTL）。
          平台 / URL 正则 / 清晰度 / 时长区间留空表示不限；时长填 <code>0</code> 表示该侧无边界。
        </p>
      </div>

      <div class="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
        <div class="px-6 py-4 flex items-center justify-between border-b border-border-light">
          <div>
            <h3 class="text-sm font-semibold text-text-primary">缓存规则</h3>
            <p class="text-xs text-text-muted mt-0.5">共 {{ rules.length }} 条规则</p>
          </div>
          <BaseButton variant="primary" size="sm" shape="square" @click="openRuleForm()">新增规则</BaseButton>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-border">
            <thead class="bg-surface-muted">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">规则</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">匹配条件</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">缓存时长</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">优先级</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">状态</th>
                <th class="px-6 py-3 text-right text-xs font-medium text-text-muted uppercase tracking-wider">操作</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-border">
              <tr v-if="rulesLoading">
                <td colspan="6"><EmptyState variant="loading" title="加载中…" /></td>
              </tr>
              <tr v-else-if="rulesError">
                <td colspan="6">
                  <EmptyState variant="error" :title="rulesError">
                    <template #action>
                      <BaseButton variant="primary" size="sm" shape="square" @click="loadRules">重试</BaseButton>
                    </template>
                  </EmptyState>
                </td>
              </tr>
              <tr v-else-if="rules.length === 0">
                <td colspan="6">
                  <EmptyState variant="empty" title="暂无缓存规则" desc="没有规则时，所有视频统一使用 24 小时缓存。" />
                </td>
              </tr>
              <template v-else>
                <tr v-for="rule in rules" :key="rule.rule_name" class="hover:bg-surface-muted">
                  <td class="px-6 py-4">
                    <p class="text-sm font-medium text-text-primary">{{ rule.rule_name }}</p>
                    <p v-if="rule.description" class="text-xs text-text-muted mt-0.5 max-w-xs">{{ rule.description }}</p>
                  </td>
                  <td class="px-6 py-4 text-xs text-text-muted">
                    <div class="flex flex-wrap gap-1.5">
                      <span class="px-2 py-0.5 rounded-full bg-surface-muted text-text-secondary">{{ rule.platform || '全部平台' }}</span>
                      <span class="px-2 py-0.5 rounded-full bg-surface-muted text-text-secondary">{{ rule.quality || '全部清晰度' }}</span>
                      <span class="px-2 py-0.5 rounded-full bg-surface-muted text-text-secondary">
                        {{ rule.min_duration ? `≥${rule.min_duration}s` : '0s' }} ~ {{ rule.max_duration ? `${rule.max_duration}s` : '∞' }}
                      </span>
                      <span v-if="rule.url_pattern" class="px-2 py-0.5 rounded-full bg-surface-muted text-text-secondary truncate max-w-[14rem]">{{ rule.url_pattern }}</span>
                    </div>
                  </td>
                  <td class="px-6 py-4 whitespace-nowrap text-sm text-text-primary">{{ formatTtl(rule.ttl_seconds) }}</td>
                  <td class="px-6 py-4 whitespace-nowrap text-sm text-text-muted">{{ rule.priority ?? 0 }}</td>
                  <td class="px-6 py-4 whitespace-nowrap">
                    <span
                      class="px-2 py-1 text-xs font-medium rounded-full"
                      :class="rule.is_active ? 'bg-success-bg text-success-text' : 'bg-neutral-bg text-neutral-text'"
                    >
                      {{ rule.is_active ? '启用' : '停用' }}
                    </span>
                  </td>
                  <td class="px-6 py-4 whitespace-nowrap text-right">
                    <BaseButton
                      variant="danger"
                      size="xs"
                      shape="square"
                      :disabled="pendingActions.has(rule.rule_name)"
                      @click="deleteRule(rule)"
                    >
                      删除
                    </BaseButton>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- ===== 解析日志 ===== -->
    <template v-else>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div class="bg-white rounded-xl border border-border shadow-sm p-4">
          <p class="text-sm text-text-muted">最近解析次数</p>
          <p class="text-2xl font-bold text-text-primary">{{ logs.length }}</p>
        </div>
        <div class="bg-white rounded-xl border border-border shadow-sm p-4">
          <p class="text-sm text-text-muted">成功率</p>
          <p class="text-2xl font-bold" :class="logSuccessRate >= 80 ? 'text-success-text' : 'text-warning-text'">{{ logSuccessRate }}%</p>
        </div>
        <div class="bg-white rounded-xl border border-border shadow-sm p-4">
          <p class="text-sm text-text-muted">平均耗时</p>
          <p class="text-2xl font-bold text-neutral-text">{{ formatDuration(logAvgDuration / 1000) }}</p>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
        <div class="px-6 py-4 flex items-center justify-between border-b border-border-light">
          <div>
            <h3 class="text-sm font-semibold text-text-primary">解析日志</h3>
            <p class="text-xs text-text-muted mt-0.5">最近 {{ logs.length }} 条解析记录</p>
          </div>
          <BaseButton variant="outline" size="sm" shape="square" :disabled="logsLoading" @click="loadLogs">
            {{ logsLoading ? '刷新中…' : '刷新' }}
          </BaseButton>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-border">
            <thead class="bg-surface-muted">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">时间</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">链接</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">结果</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">耗时</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">详情</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-border">
              <tr v-if="logsLoading">
                <td colspan="5"><EmptyState variant="loading" title="加载中…" /></td>
              </tr>
              <tr v-else-if="logsError">
                <td colspan="5">
                  <EmptyState variant="error" :title="logsError">
                    <template #action>
                      <BaseButton variant="primary" size="sm" shape="square" @click="loadLogs">重试</BaseButton>
                    </template>
                  </EmptyState>
                </td>
              </tr>
              <tr v-else-if="logs.length === 0">
                <td colspan="5">
                  <EmptyState variant="empty" title="暂无解析日志" desc="每次解析视频后会自动记录一条结果。" />
                </td>
              </tr>
              <template v-else>
                <tr v-for="log in logs" :key="log.id" class="hover:bg-surface-muted">
                  <td class="px-6 py-3 whitespace-nowrap text-xs text-text-muted">{{ formatDate(log.created_at) }}</td>
                  <td class="px-6 py-3 text-xs text-text-secondary">
                    <span class="block truncate max-w-sm">{{ log.url || '—' }}</span>
                  </td>
                  <td class="px-6 py-3 whitespace-nowrap">
                    <span
                      class="px-2 py-1 text-xs font-medium rounded-full"
                      :class="log.success ? 'bg-success-bg text-success-text' : 'bg-error-bg text-error-text'"
                    >
                      {{ log.success ? '成功' : '失败' }}
                    </span>
                  </td>
                  <td class="px-6 py-3 whitespace-nowrap text-xs text-text-muted">{{ log.duration_ms ? `${log.duration_ms} ms` : '—' }}</td>
                  <td class="px-6 py-3 text-xs text-text-muted">
                    <span class="block truncate max-w-md">{{ log.error_message || log.message || '—' }}</span>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- 视频播放模态框 -->
    <BaseModal v-model="showPlayerModal" title="视频播放" max-width="4xl">
      <video
        ref="playerRef"
        :src="currentVideo?.direct_url || currentVideo?.download_url"
        controls
        autoplay
        class="w-full rounded-lg"
      >
        您的浏览器不支持视频播放
      </video>
      <div class="mt-4">
        <p class="font-medium">{{ currentVideo?.title }}</p>
        <p class="text-sm text-text-muted">{{ currentVideo?.platform }}</p>
      </div>
    </BaseModal>

    <!-- 导出对话框 -->
    <BaseModal v-model="showExportDialog" title="导出数据" max-width="md">
      <div class="px-6 py-2 space-y-4">
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1">导出格式</label>
          <select v-model="exportFormat" class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all">
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1">筛选条件</label>
          <div class="space-y-2">
            <label class="flex items-center gap-2">
              <input v-model="exportFilters.platform" type="checkbox" class="rounded border-border text-primary focus:ring-primary/20" />
              <span class="text-sm text-text-secondary">按平台筛选</span>
            </label>
            <label class="flex items-center gap-2">
              <input v-model="exportFilters.cacheStatus" type="checkbox" class="rounded border-border text-primary focus:ring-primary/20" />
              <span class="text-sm text-text-secondary">按状态筛选</span>
            </label>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-3 px-6 pb-6">
          <BaseButton variant="outline" size="sm" shape="square" :disabled="exporting" @click="showExportDialog = false">取消</BaseButton>
          <BaseButton variant="primary" size="sm" shape="square" :disabled="exporting" @click="exportData">
            {{ exporting ? '导出中…' : '导出' }}
          </BaseButton>
        </div>
      </template>
    </BaseModal>

    <!-- 新增/编辑缓存规则 -->
    <BaseModal
      v-model="showRuleModal"
      :title="ruleForm.rule_name ? '编辑缓存规则' : '新增缓存规则'"
      subtitle="留空的匹配条件表示不限；时长填 0 表示该侧无边界"
      max-width="2xl"
    >
      <form class="grid grid-cols-1 sm:grid-cols-2 gap-4" @submit.prevent="saveRule">
        <div class="sm:col-span-2">
          <label class="block text-sm font-medium text-text-primary mb-1" for="rule-name">规则名</label>
          <input
            id="rule-name"
            v-model="ruleForm.rule_name"
            type="text"
            required
            placeholder="例如 short_video"
            class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1" for="rule-platform">平台</label>
          <input
            id="rule-platform"
            v-model="ruleForm.platform"
            type="text"
            placeholder="留空 = 全部平台"
            class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1" for="rule-quality">清晰度</label>
          <input
            id="rule-quality"
            v-model="ruleForm.quality"
            type="text"
            placeholder="留空 = 全部清晰度"
            class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
        </div>
        <div class="sm:col-span-2">
          <label class="block text-sm font-medium text-text-primary mb-1" for="rule-pattern">URL 正则</label>
          <input
            id="rule-pattern"
            v-model="ruleForm.url_pattern"
            type="text"
            placeholder="留空 = 不限制，例如 ^https://www\.bilibili\.com"
            class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1" for="rule-min">最小时长（秒）</label>
          <input
            id="rule-min"
            v-model.number="ruleForm.min_duration"
            type="number"
            min="0"
            class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1" for="rule-max">最大时长（秒）</label>
          <input
            id="rule-max"
            v-model.number="ruleForm.max_duration"
            type="number"
            min="0"
            class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1" for="rule-ttl">缓存时长（秒）</label>
          <input
            id="rule-ttl"
            v-model.number="ruleForm.ttl_seconds"
            type="number"
            min="1"
            required
            class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1" for="rule-priority">优先级</label>
          <input
            id="rule-priority"
            v-model.number="ruleForm.priority"
            type="number"
            min="0"
            class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
        </div>
        <div class="sm:col-span-2">
          <label class="block text-sm font-medium text-text-primary mb-1" for="rule-desc">说明</label>
          <input
            id="rule-desc"
            v-model="ruleForm.description"
            type="text"
            placeholder="可选，用于在列表里说明这条规则的用途"
            class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
        </div>
      </form>
      <template #footer>
        <div class="flex justify-end gap-3 px-6 pb-6">
          <BaseButton variant="outline" size="sm" shape="square" :disabled="savingRule" @click="showRuleModal = false">取消</BaseButton>
          <BaseButton variant="primary" size="sm" shape="square" :disabled="savingRule" @click="saveRule">
            {{ savingRule ? '保存中…' : '保存' }}
          </BaseButton>
        </div>
      </template>
    </BaseModal>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import request from '../utils/request.js'
import { copyText } from '../utils/clipboard.js'
import { downloadBlob } from '../utils/file.js'
import { formatBytes, formatTime, formatDateTime } from '../utils/format.js'
import { getApiError } from '../utils/error.js'
import EmptyState from './ui/EmptyState.vue'
import VideoThumbnail from './VideoThumbnail.vue'
import BaseButton from './ui/BaseButton.vue'
import BaseModal from './ui/BaseModal.vue'

// 业务 success:false 与异常 catch 分支的兜底文案（统一提取，避免 4 处重复）。
const OPERATION_FAILED_TIP = '操作失败，请重试'
const DELETE_FAILED_TIP = '删除失败'
const CLEANUP_FAILED_TIP = '清理失败'

const videos = ref([])
const stats = ref({})
const total = ref(0)
const currentPage = ref(1)
const pageSize = 50
// 进行中的行级操作（按 video_url 记录）：防止同一条记录被重复点击并发提交
const pendingActions = ref(new Set())
// 清理 / 导出为全局操作，用独立标志禁用按钮（避免连点触发多次请求）
const cleaningUp = ref(false)
const exporting = ref(false)

const filters = ref({
  search: '',
  platform: '',
  cacheStatus: '',
  hotOnly: false
})

const showPlayerModal = ref(false)
const currentVideo = ref(null)
const playerRef = ref(null)

const showExportDialog = ref(false)
const exportFormat = ref('json')
const exportFilters = ref({
  platform: false,
  cacheStatus: false
})

// ===== 分区（缓存条目 / 缓存规则 / 解析日志）=====
const TABS = [
  { key: 'videos', label: '缓存条目' },
  { key: 'rules', label: '缓存规则' },
  { key: 'logs', label: '解析日志' }
]
const activeTab = ref('videos')

function switchTab(key) {
  if (activeTab.value === key) return
  activeTab.value = key
  // 按需加载：切到哪个分区才拉哪个数据，避免一次打开就请求三套接口
  if (key === 'rules' && !rulesLoaded.value) loadRules()
  if (key === 'logs' && !logsLoaded.value) loadLogs()
}

// ===== 缓存规则 =====
const rules = ref([])
const rulesLoading = ref(false)
const rulesError = ref('')
const rulesLoaded = ref(false)
const showRuleModal = ref(false)
const savingRule = ref(false)
const emptyRuleForm = () => ({
  rule_name: '',
  rule_type: 'ttl',
  platform: '',
  url_pattern: '',
  quality: '',
  min_duration: 0,
  max_duration: 0,
  ttl_seconds: 86400,
  priority: 0,
  is_active: true,
  description: ''
})
const ruleForm = ref(emptyRuleForm())

// ===== 解析日志 =====
const logs = ref([])
const logsLoading = ref(false)
const logsError = ref('')
const logsLoaded = ref(false)

// 加载 / 错误状态；轻提示统一走全局 showToast（provide 于 App.vue）
const loading = ref(false)
const errorMsg = ref('')
// 403：当前账号不是管理员（服务端 ADMIN_EMAILS 白名单），整个面板渲染无权限状态
const forbidden = ref(false)
const showToast = inject('showToast', () => {})

onMounted(() => {
  loadStats()
  loadVideos()
})

// 403 统一识别：缓存后台的全部读/写接口都要求管理员，
// 非管理员访问时直接切到「需要管理员权限」状态，而不是逐个接口报错。
function isForbidden(error) {
  return error?.response?.status === 403
}

async function loadStats() {
  try {
    const response = await request.get('/video-cache/stats', { __silent: true })
    if (response.data.success) {
      stats.value = response.data.data
    }
  } catch (error) {
    // 修复：原写法仅 console.error，用户看不到统计卡为何一直空白。
    // __silent 抑制 axios 自动 toast，这里手动补一条让用户知道。
    console.error('加载统计信息失败:', error)
    if (isForbidden(error)) {
      forbidden.value = true
      return
    }
    showToast(getApiError(error, '加载统计失败'), 'error')
  }
}

// ===== 缓存规则 / 解析日志 =====
async function loadRules() {
  rulesLoading.value = true
  rulesError.value = ''
  try {
    const response = await request.get('/video-cache/rules', { __silent: true })
    if (response.data.success) {
      rules.value = response.data.data || []
    } else {
      rulesError.value = getApiError({ response }, '加载失败', '未知错误')
    }
  } catch (error) {
    rulesError.value = getApiError(error, '加载缓存规则失败')
  } finally {
    rulesLoading.value = false
    rulesLoaded.value = true
  }
}

function openRuleForm(rule = null) {
  ruleForm.value = rule
    ? {
        rule_name: rule.rule_name || '',
        rule_type: rule.rule_type || 'ttl',
        platform: rule.platform || '',
        url_pattern: rule.url_pattern || '',
        quality: rule.quality || '',
        min_duration: rule.min_duration ?? 0,
        max_duration: rule.max_duration ?? 0,
        ttl_seconds: rule.ttl_seconds ?? 86400,
        priority: rule.priority ?? 0,
        is_active: !!rule.is_active,
        description: rule.description || ''
      }
    : emptyRuleForm()
  showRuleModal.value = true
}

async function saveRule() {
  const form = ruleForm.value
  if (!form.rule_name.trim()) {
    showToast('请填写规则名', 'error')
    return
  }
  savingRule.value = true
  try {
    const response = await request.post('/video-cache/rules', { ...form }, { __silent: true })
    if (response.data.success) {
      showToast('缓存规则已保存', 'success')
      showRuleModal.value = false
      loadRules()
    } else {
      showToast(response.data.message || '保存失败', 'error')
    }
  } catch (error) {
    console.error('保存缓存规则失败:', error)
    showToast(getApiError(error, '保存缓存规则失败'), 'error')
  } finally {
    savingRule.value = false
  }
}

async function deleteRule(rule) {
  if (!confirm(`确定要删除缓存规则「${rule.rule_name}」吗？`)) return
  if (pendingActions.value.has(rule.rule_name)) return
  pendingActions.value.add(rule.rule_name)
  try {
    const response = await request.delete(`/video-cache/rules/${encodeURIComponent(rule.rule_name)}`, { __silent: true })
    if (response.data.success) {
      showToast('缓存规则已删除', 'success')
      loadRules()
    } else {
      showToast(response.data.message || '删除失败', 'error')
    }
  } catch (error) {
    console.error('删除缓存规则失败:', error)
    showToast(getApiError(error, '删除缓存规则失败'), 'error')
  } finally {
    pendingActions.value.delete(rule.rule_name)
  }
}

async function loadLogs() {
  logsLoading.value = true
  logsError.value = ''
  try {
    const response = await request.get('/video-cache/logs', { params: { limit: 100 }, __silent: true })
    if (response.data.success) {
      logs.value = response.data.data || []
    } else {
      logsError.value = getApiError({ response }, '加载失败', '未知错误')
    }
  } catch (error) {
    logsError.value = getApiError(error, '加载解析日志失败')
  } finally {
    logsLoading.value = false
    logsLoaded.value = true
  }
}

// 解析日志派生指标：成功率与平均耗时（仅统计有耗时记录的条目）
const logSuccessRate = computed(() => {
  if (!logs.value.length) return 0
  const ok = logs.value.filter((l) => l.success).length
  return Math.round((ok / logs.value.length) * 100)
})

const logAvgDuration = computed(() => {
  const timed = logs.value.filter((l) => Number(l.duration_ms) > 0)
  if (!timed.length) return 0
  return Math.round(timed.reduce((sum, l) => sum + Number(l.duration_ms), 0) / timed.length)
})

async function loadVideos() {
  loading.value = true
  errorMsg.value = ''
  try {
    const params = {
      limit: pageSize,
      offset: (currentPage.value - 1) * pageSize
    }
    
    if (filters.value.search) {
      params.search = filters.value.search
    }
    if (filters.value.platform) {
      params.platform = filters.value.platform
    }
    if (filters.value.cacheStatus) {
      params.cache_status = filters.value.cacheStatus
    }
    if (filters.value.hotOnly) {
      params.hot_only = true
    }
    
    const response = await request.get('/video-cache/videos', { params, __silent: true })
    if (response.data.success) {
      videos.value = response.data.data
      total.value = response.data.total
    } else {
      errorMsg.value = getApiError({ response }, '加载失败', '未知错误')
    }
  } catch (error) {
    if (isForbidden(error)) {
      forbidden.value = true
      return
    }
    errorMsg.value = getApiError(error, '加载失败')
  } finally {
    loading.value = false
  }
}

// 搜索 / 筛选变更统一入口：必须把页码重置回第 1 页。
// 否则在第 N 页切换平台/状态/仅热门时，仍以原 offset 请求新筛选结果集，
// offset 越界 → 列表空白、分页文案与总数矛盾。
function applyFilters() {
  currentPage.value = 1
  loadVideos()
}

function searchVideos() {
  applyFilters()
}

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
    loadVideos()
  }
}

function nextPage() {
  currentPage.value++
  loadVideos()
}

function playVideo(video) {
  currentVideo.value = video
  showPlayerModal.value = true
}

function downloadVideo(video) {
  if (!video.download_url) {
    showToast('该缓存没有可用的下载直链', 'error')
    return
  }
  // 修复：原 `_blank` 在老浏览器（IE / 旧 Safari）下会暴露 window.opener 引用，可能被目标页面反向操控。
  // 显式 noopener,noreferrer 是现代安全标准。
  const win = window.open(video.download_url, '_blank', 'noopener,noreferrer')
  // window.open 返回 null = 弹窗被浏览器拦截。原实现静默失败，用户点了没反应也不知道原因。
  if (!win) {
    copyText(video.download_url).then((ok) => {
      showToast(
        ok ? '新窗口被拦截，下载链接已复制到剪贴板' : '新窗口被拦截，请手动复制下载链接',
        ok ? 'warning' : 'error'
      )
    })
  }
}

async function copyUrl(url) {
  const ok = await copyText(url)
  showToast(ok ? '链接已复制到剪贴板' : '复制失败', ok ? 'success' : 'error')
}

async function markHot(video) {
  if (pendingActions.value.has(video.video_url)) return
  pendingActions.value.add(video.video_url)
  try {
    const response = await request.put(`/video-cache/videos/${encodeURIComponent(video.video_url)}/hot`, {}, { __silent: true })
    if (response.data.success) {
      showToast('已标记为热门', 'success')
      loadVideos()
      loadStats()
    } else {
      showToast(OPERATION_FAILED_TIP, 'error')
    }
  } catch (error) {
    console.error('标记热门失败:', error)
    showToast(getApiError(error, '', OPERATION_FAILED_TIP), 'error')
  } finally {
    pendingActions.value.delete(video.video_url)
  }
}

async function deleteVideo(video) {
  if (!confirm(`确定要删除 "${video.title}" 的缓存吗？`)) {
    return
  }
  if (pendingActions.value.has(video.video_url)) return
  pendingActions.value.add(video.video_url)

  try {
    const response = await request.delete(`/video-cache/videos/${encodeURIComponent(video.video_url)}`, { __silent: true })
    if (response.data.success) {
      showToast('删除成功', 'success')
      // 删除的是本页最后一条且不在第 1 页时回退一页：否则仍按原 offset 请求，
      // 会停留在越界的空白页（分页按钮却显示还有数据）。
      if (videos.value.length === 1 && currentPage.value > 1) {
        currentPage.value--
      }
      loadVideos()
      loadStats()
    } else {
      showToast(DELETE_FAILED_TIP, 'error')
    }
  } catch (error) {
    console.error('删除失败:', error)
    showToast(getApiError(error, '', DELETE_FAILED_TIP), 'error')
  } finally {
    pendingActions.value.delete(video.video_url)
  }
}

async function cleanupExpired() {
  if (!confirm('确定要清理所有过期缓存吗？')) {
    return
  }
  if (cleaningUp.value) return
  cleaningUp.value = true

  try {
    const response = await request.post('/video-cache/cleanup', {}, { __silent: true })
    if (response.data.success) {
      showToast(response.data.message || '清理完成', 'success')
      // 清理会删除若干记录，当前页码很可能越界；重置回第 1 页再加载。
      currentPage.value = 1
      loadVideos()
      loadStats()
    } else {
      showToast(CLEANUP_FAILED_TIP, 'error')
    }
  } catch (error) {
    console.error('清理失败:', error)
    showToast(getApiError(error, '', CLEANUP_FAILED_TIP), 'error')
  } finally {
    cleaningUp.value = false
  }
}

async function exportData() {
  if (exporting.value) return
  exporting.value = true
  try {
    const params = {}

    if (exportFilters.value.platform && filters.value.platform) {
      params.platform = filters.value.platform
    }
    if (exportFilters.value.cacheStatus && filters.value.cacheStatus) {
      params.cache_status = filters.value.cacheStatus
    }

    const response = await request.get(`/video-cache/export?format=${exportFormat.value}`, {
      params,
      responseType: 'blob',
      __silent: true
    })

    // 复用 utils/file.js#downloadBlob（自动延迟 1s revoke，避免 Firefox 大文件下载失败）
    const blob = new Blob([response.data])
    downloadBlob(blob, `video_cache_export.${exportFormat.value}`)

    showExportDialog.value = false
    showToast('导出成功', 'success')
  } catch (error) {
    console.error('导出失败:', error)
    showToast('导出失败', 'error')
  } finally {
    exporting.value = false
  }
}

function isPlayableUrl(url) {
  if (!url) return false
  return url.endsWith('.mp4') || url.endsWith('.webm') || url.includes('.m3u8')
}

function getPlatformClass(platform) {
  // 平台标签沿用各品牌色（识别性优先），但统一走语义 token 体系，
  // 未知平台回落到中性底色，不再直接用 Tailwind 内置灰。
  const classes = {
    youtube: 'bg-error-bg text-error-text',
    bilibili: 'bg-pink-100 text-pink-700',
    douyin: 'bg-black text-white',
    twitter: 'bg-info-bg text-info-text'
  }
  return classes[platform?.toLowerCase()] || 'bg-surface-muted text-text-secondary'
}

function getStatusClass(status) {
  return status === 'active' ? 'bg-success-bg text-success-text' : 'bg-surface-muted text-text-secondary'
}

function formatDuration(seconds) {
  // 复用 utils/format.js#formatTime（mm:ss / hh:mm:ss），空值用 '-' 兜底（统一后台展示口径）
  return seconds ? formatTime(seconds) : '-'
}

function formatFileSize(bytes) {
  return bytes ? formatBytes(bytes, 2) : '-'
}

function formatDate(dateStr) {
  // 复用 utils/format.js#formatDateTime（本地化日期+时间），空值用 '-' 兜底
  return dateStr ? formatDateTime(dateStr) : '-'
}

function formatTtl(seconds) {
  const n = Number(seconds)
  if (!Number.isFinite(n) || n <= 0) return '默认 24 小时'
  if (n % 86400 === 0) return `${n / 86400} 天`
  if (n % 3600 === 0) return `${n / 3600} 小时`
  return `${n} 秒`
}
</script>

<style scoped>
.video-cache-admin {
  padding: 1rem;
}
</style>
