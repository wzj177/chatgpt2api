<template>
  <div class="flex min-h-0 flex-col space-y-4">
    <MetricStrip
      :items="summaryItems"
      density="compact"
      columns-class="grid-cols-2 xl:grid-cols-5"
    />

    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <p class="text-xs text-muted-foreground">共 {{ userKeysTotal }} 位用户</p>
        <span v-if="selectedIds.length" class="text-xs text-muted-foreground">已选 {{ selectedIds.length }} 位</span>
      </div>
      <ConsoleSegmentedTabs
        v-model="sortMode"
        class="max-w-xs"
        fit="content"
        :options="sortOptions"
        aria-label="用户排序"
      />
      <ConsoleSegmentedTabs
        v-model="registrationSourceMode"
        class="max-w-md"
        fit="content"
        :options="registrationSourceOptions"
        aria-label="注册来源筛选"
      />
    </div>

    <div v-if="selectedIds.length" class="flex flex-wrap items-center gap-3 rounded-md border border-border bg-muted/20 p-3">
      <span class="text-xs text-muted-foreground">增加今日剩余次数</span>
      <Input v-model="bonusCount" type="number" min="1" max="10000" class="w-24" aria-label="增加今日次数" />
      <Button size="sm" variant="primary" :disabled="userKeyBusy !== ''" @click="adjustSelectedUsers">
        {{ userKeyBusy === 'bulk-daily-image' ? '调整中...' : '确认增加' }}
      </Button>
      <Button size="sm" variant="outline" :disabled="userKeyBusy !== ''" @click="selectedIds = []">取消选择</Button>
    </div>

    <PageLoadingState v-if="userKeysLoading" compact title="正在加载用户" description="读取用户列表和用量统计。" />
    <StateBlock v-else-if="sortedUsers.length === 0" compact dashed>
      暂无用户。公开注册成功后会自动出现在这里。
    </StateBlock>
    <TableShell
      v-else
      class="users-table"
      :fill="workspaceLayout"
      :scroll-mode="workspaceLayout ? 'contained' : 'page'"
      hover-rows
      sticky-header
      unframed
      :scroll-class="workspaceLayout ? 'max-h-[min(42rem,60dvh)] lg:max-h-none' : ''"
      table-class="w-full min-w-[900px] table-fixed"
      head-class="normal-case tracking-normal"
      style="--table-shell-footer-padding: 12px 0 0"
    >
      <template #head>
        <tr>
          <th class="w-[27%] py-3 pl-4 pr-5">
            <Checkbox :model-value="allVisibleSelected" aria-label="选择当前页用户" @update:model-value="toggleAllVisible" />
            <span class="ml-2">用户</span>
          </th>
          <th class="w-[20%] py-3 pr-5">注册与登录</th>
          <th class="w-[13%] py-3 pr-5">注册来源</th>
          <th class="w-[18%] py-3 pr-5">成功生图</th>
          <th class="w-[22%] py-3 pr-4 text-right">操作</th>
        </tr>
      </template>

      <tr
        v-for="item in sortedUsers"
        :key="item.id"
        class="border-b border-border last:border-b-0"
      >
        <td class="min-w-0 py-3 pl-4 pr-5 align-top">
          <Checkbox :model-value="selectedIds.includes(item.id)" :aria-label="`选择${item.name || item.id}`" @update:model-value="toggleUser(item.id, $event)" />
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
        </td>

        <td class="py-3 pr-5 align-top text-xs text-muted-foreground">
          <p>注册：{{ formatDateTime(item.created_at) }}</p>
          <p class="mt-1">最近登录：{{ formatDateTime(item.last_used_at) }}</p>
        </td>

        <td class="py-3 pr-5 align-top text-xs text-muted-foreground">
          {{ item.registration_source_label }}
        </td>

        <td class="py-3 pr-5 align-top text-xs">
          <div class="grid grid-cols-3 gap-3">
            <div>
              <p class="text-muted-foreground">今日成功</p>
              <p class="mt-1 font-semibold tabular-nums text-foreground">{{ item.daily_image_count || 0 }}</p>
            </div>
            <div>
              <p class="text-muted-foreground">当日剩余</p>
              <p class="mt-1 font-semibold tabular-nums text-foreground">{{ item.daily_image_remaining || 0 }}</p>
              <p class="mt-1 text-xs text-muted-foreground">当日可用 {{ item.daily_image_base_remaining || 0 }}</p>
              <p v-if="item.daily_image_bonus" class="mt-1 text-xs text-emerald-600">额外 +{{ item.daily_image_bonus }}</p>
            </div>
            <div>
              <p class="text-muted-foreground">累计成功</p>
              <p class="mt-1 font-semibold tabular-nums text-foreground">{{ item.usage_count || 0 }}</p>
            </div>
          </div>
        </td>

        <td class="py-3 pr-4 align-top">
          <div class="flex flex-wrap items-center justify-end gap-2">
            <Button size="xs" variant="outline" :disabled="userKeyBusy === item.id" @click="$emit('edit', item)">编辑</Button>
            <Button size="xs" variant="outline" :disabled="userKeyBusy === item.id" @click="$emit('toggle', item)">
              {{ item.enabled ? '禁用' : '启用' }}
            </Button>
            <Button size="xs" variant="outline" root-class="text-rose-600" :disabled="userKeyBusy === item.id" @click="$emit('delete', item)">删除</Button>
          </div>
        </td>
      </tr>

      <template #footer>
        <ListPagination
          :page="currentPage"
          :page-size="pageSize"
          :total-count="userKeysTotal"
          :page-size-options="pageSizeOptions"
          unit="位用户"
          :disabled="userKeysLoading"
          @update:page="$emit('update:currentPage', $event)"
          @update:page-size="$emit('update:pageSize', $event)"
        />
      </template>
    </TableShell>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, Checkbox, Input, TableShell } from 'nanocat-ui'
import type { SegmentedValue } from 'nanocat-ui'
import ListPagination from '@/components/ai/ListPagination.vue'
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
  workspaceLayout: boolean
  currentPage: number
  pageSize: number
  registrationSource: string
  pageSizeOptions: number[]
  userKeysTotal: number
}>()

const emit = defineEmits<{
  'update:currentPage': [value: number]
  'update:pageSize': [value: number]
  'update:registrationSource': [value: string]
  edit: [item: UserKey]
  toggle: [item: UserKey]
  delete: [item: UserKey]
  adjustDailyImages: [userIds: string[], count: number]
}>()

const sortMode = ref<SegmentedValue>('last_used')
const selectedIds = ref<string[]>([])
const bonusCount = ref(1)
const allVisibleSelected = computed(() => (
  props.userKeys.length > 0 && props.userKeys.every(item => selectedIds.value.includes(item.id))
))

function toggleUser(userId: string, selected: boolean) {
  selectedIds.value = selected
    ? Array.from(new Set([...selectedIds.value, userId]))
    : selectedIds.value.filter(id => id !== userId)
}

function toggleAllVisible(selected: boolean) {
  const visibleIds = props.userKeys.map(item => item.id)
  selectedIds.value = selected
    ? Array.from(new Set([...selectedIds.value, ...visibleIds]))
    : selectedIds.value.filter(id => !visibleIds.includes(id))
}

function adjustSelectedUsers() {
  const count = Math.trunc(Number(bonusCount.value))
  if (!Number.isFinite(count) || count < 1 || count > 10000) return
  emit('adjustDailyImages', [...selectedIds.value], count)
}

watch(() => props.userKeys, () => {
  const visibleIds = new Set(props.userKeys.map(item => item.id))
  selectedIds.value = selectedIds.value.filter(id => visibleIds.has(id))
}, { deep: false })

const registrationSourceMode = ref<SegmentedValue>(props.registrationSource as SegmentedValue)
watch(() => props.registrationSource, (value) => {
  if (value !== String(registrationSourceMode.value)) {
    registrationSourceMode.value = value as SegmentedValue
  }
})
watch(registrationSourceMode, (value) => {
  const nextValue = String(value)
  console.info('[用户管理] 来源控件已选择', { value: nextValue, parentValue: props.registrationSource })
  if (nextValue !== props.registrationSource) {
    emit('update:registrationSource', nextValue)
  }
})
const registrationSourceOptions = [
  { value: 'all', label: '全部来源' },
  { value: 'email', label: '邮箱注册' },
  { value: 'linuxdo', label: 'Linux.do' },
]
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
  {
    key: 'remaining-quota',
    label: '总剩余额度',
    value: props.userStats?.total_quota ?? 0,
    meta: props.userStats?.unknown_quota_count ? '存在未确认额度' : '',
  },
])
</script>
