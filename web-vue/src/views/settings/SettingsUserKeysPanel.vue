<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="ui-section-title">用户管理</p>
        <p class="mt-1 text-xs text-muted-foreground">查看注册邮箱、用户名、登录时间和成功生图用量。</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" :disabled="userKeysLoading" @click="$emit('load')">
          {{ userKeysLoading ? '刷新中...' : '刷新用户' }}
        </Button>
        <Button size="sm" variant="primary" :disabled="userKeyBusy === 'create'" @click="$emit('create')">
          创建用户
        </Button>
      </div>
    </div>

    <MetricStrip
      :items="summaryItems"
      density="compact"
      columns-class="grid-cols-2 xl:grid-cols-4"
    />

    <div v-if="newUserKey" class="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="font-medium">新密钥只展示一次，请现在复制保存。</p>
          <p class="mt-2 break-all font-mono text-xs">{{ newUserKey }}</p>
        </div>
        <Button size="xs" variant="outline" root-class="shrink-0 border-emerald-200 bg-white text-emerald-700" @click="$emit('copy', newUserKey)">
          复制
        </Button>
      </div>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-xs text-muted-foreground">共 {{ userKeys.length }} 位用户</p>
      <ConsoleSegmentedTabs
        v-model="sortMode"
        class="max-w-xs"
        fit="content"
        :options="sortOptions"
        aria-label="用户排序"
      />
    </div>

    <PageLoadingState v-if="userKeysLoading" compact title="正在加载用户" description="读取用户列表和用量统计。" />
    <StateBlock v-else-if="sortedUsers.length === 0" compact dashed>
      暂无用户。公开注册成功后会自动出现在这里。
    </StateBlock>
    <div v-else class="overflow-hidden rounded-md border border-border">
      <div
        v-for="item in sortedUsers"
        :key="item.id"
        class="grid gap-3 border-b border-border px-4 py-3 last:border-b-0 lg:grid-cols-[minmax(12rem,1.2fr)_minmax(12rem,1.4fr)_minmax(10rem,1fr)_auto] lg:items-center"
      >
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <p class="truncate text-sm font-medium text-foreground">{{ item.name || '普通用户' }}</p>
            <StateBadge :tone="item.enabled ? 'success' : 'muted'" size="xs" shape="rounded">
              {{ item.enabled ? '已启用' : '已禁用' }}
            </StateBadge>
            <StateBadge tone="muted" size="xs" shape="rounded">
              {{ item.email ? '注册用户' : '后台用户' }}
            </StateBadge>
          </div>
          <p class="mt-1 truncate text-xs text-muted-foreground">{{ item.email || item.id }}</p>
          <p v-if="item.phone" class="mt-1 text-xs text-muted-foreground">{{ item.phone }}</p>
        </div>

        <div class="text-xs text-muted-foreground">
          <p>注册：{{ formatDateTime(item.created_at) }}</p>
          <p class="mt-1">最近登录：{{ formatDateTime(item.last_used_at) }}</p>
        </div>

        <div class="grid grid-cols-2 gap-2 text-xs">
          <div>
            <p class="text-muted-foreground">今日成功</p>
            <p class="mt-1 font-semibold tabular-nums text-foreground">{{ item.daily_image_count || 0 }}</p>
          </div>
          <div>
            <p class="text-muted-foreground">累计成功</p>
            <p class="mt-1 font-semibold tabular-nums text-foreground">{{ item.usage_count || 0 }}</p>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2 lg:justify-end">
          <Button size="xs" variant="outline" :disabled="userKeyBusy === item.id" @click="$emit('edit', item)">编辑</Button>
          <Button size="xs" variant="outline" :disabled="userKeyBusy === item.id" @click="$emit('toggle', item)">
            {{ item.enabled ? '禁用' : '启用' }}
          </Button>
          <Button size="xs" variant="outline" root-class="text-rose-600" :disabled="userKeyBusy === item.id" @click="$emit('delete', item)">删除</Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button } from 'nanocat-ui'
import type { SegmentedValue } from 'nanocat-ui'
import type { UserKey, UserStats } from '@/api/userKeys'
import ConsoleSegmentedTabs from '@/components/ai/ConsoleSegmentedTabs.vue'
import MetricStrip from '@/components/ai/MetricStrip.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import { formatDateTime } from '@/views/settings/settingsView'

const props = defineProps<{
  userKeys: UserKey[]
  userStats: UserStats | null
  userKeysLoading: boolean
  userKeyBusy: string
  newUserKey: string
}>()

defineEmits<{
  load: []
  create: []
  copy: [value: string]
  edit: [item: UserKey]
  toggle: [item: UserKey]
  delete: [item: UserKey]
}>()

const sortMode = ref<SegmentedValue>('last_used')
const sortOptions = [
  { value: 'last_used', label: '最近登录' },
  { value: 'usage', label: '使用次数' },
]

const sortedUsers = computed(() => [...props.userKeys].sort((left, right) => {
  if (sortMode.value === 'usage') {
    return Number(right.usage_count || 0) - Number(left.usage_count || 0)
  }
  return String(right.last_used_at || '').localeCompare(String(left.last_used_at || ''))
}))

const summaryItems = computed(() => [
  { key: 'registered', label: '累计注册', value: props.userStats?.total_registered ?? 0 },
  { key: 'active', label: '今日活跃', value: props.userStats?.active_today ?? 0 },
  { key: 'today-images', label: '今日成功生图', value: props.userStats?.images_today ?? 0 },
  {
    key: 'total-images',
    label: '累计成功生图',
    value: props.userStats?.total_usage ?? 0,
    meta: props.userStats ? `单用户每日上限 ${props.userStats.daily_image_limit || '不限'}` : '',
  },
])
</script>
