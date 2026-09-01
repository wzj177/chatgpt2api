import { ref, watch } from 'vue'

import { userKeysApi, type UserKey, type UserStats } from '@/api/userKeys'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import type { usePageRuntime } from '@/composables/usePageRuntime'
import { usePageDebouncedAction, usePageQuery, usePagedQuery } from '@/composables/usePageQuery'
import { useToast } from '@/composables/useToast'
import { errorMessage } from '@/lib/errorMessage'

export type UserKeyForm = {
  name: string
  key: string
}

type SettingsUserKeysRuntimeOptions = {
  runtime: ReturnType<typeof usePageRuntime>
  requestKey: string
}

function createUserKeyForm(): UserKeyForm {
  return { name: '', key: '' }
}

export function useSettingsUserKeysRuntime(options: SettingsUserKeysRuntimeOptions) {
  const pageSize = ref(10)
  const registrationSource = ref('all')
  const userSearch = ref('')
  const userKeys = ref<UserKey[]>([])
  const userKeysLoaded = ref(false)
  const userKeysLoading = ref(false)
  const userStats = ref<UserStats | null>(null)
  const userKeyBusy = ref('')
  const userKeyModal = ref<'edit' | ''>('')
  const editingUserKey = ref<UserKey | null>(null)
  const userKeyForm = ref<UserKeyForm>(createUserKeyForm())
  const toast = useToast()
  const confirmDialog = useConfirmDialog()

  function upsertUserKey(item: UserKey) {
    const index = userKeys.value.findIndex(candidate => candidate.id === item.id)
    if (index < 0) {
      userKeys.value = [...userKeys.value, item]
      return
    }
    userKeys.value = userKeys.value.map(candidate => candidate.id === item.id ? item : candidate)
  }

  const userKeysQuery = usePagedQuery({
    runtime: options.runtime,
    key: options.requestKey,
    pageSize,
    loading: userKeysLoading,
    errorMessage: '加载用户密钥失败',
    fetch: ({ page, pageSize: size }) => {
      const params = {
        page,
        page_size: size,
        registration_source: registrationSource.value,
        keyword: userSearch.value.trim(),
      }
      console.info('[用户管理] 请求用户列表', params)
      return userKeysApi.list(params)
    },
    resolvePage: response => response.page,
    resolvePageCount: response => Math.max(1, Math.ceil(response.total / Math.max(1, response.page_size))),
    resolveTotal: response => response.total,
    apply: (response) => {
      userKeys.value = Array.isArray(response.items) ? response.items : []
      userKeysLoaded.value = true
    },
    onError: (message) => {
      userKeys.value = []
      toast.error(message)
    },
  })
  const userStatsQuery = usePageQuery({
    runtime: options.runtime,
    key: `${options.requestKey}:stats`,
    errorMessage: '加载用户统计失败',
  })
  watch(pageSize, () => {
    void userKeysQuery.resetAndLoad()
  })
  watch(registrationSource, (value, previousValue) => {
    console.info('[用户管理] 注册来源已切换', { previousValue, value })
    void userKeysQuery.resetAndLoad()
  })
  const searchDebounce = usePageDebouncedAction({
    runtime: options.runtime,
    key: `${options.requestKey}:search`,
    delayMs: 250,
    action: () => userKeysQuery.resetAndLoad(),
  })
  watch(userSearch, () => {
    searchDebounce.schedule()
  })

  function resetUserKeyForm() {
    userKeyForm.value = createUserKeyForm()
    editingUserKey.value = null
  }

  function openUserKeyEditModal(item: UserKey) {
    editingUserKey.value = item
    userKeyForm.value = {
      name: item.name || '',
      key: '',
    }
    userKeyModal.value = 'edit'
  }

  function closeUserKeyModal() {
    if (editingUserKey.value && userKeyBusy.value === editingUserKey.value.id) return
    userKeyModal.value = ''
    resetUserKeyForm()
  }

  async function loadUserKeys() {
    await Promise.all([
      userKeysQuery.resetAndLoad(),
      userStatsQuery.run(
        () => userKeysApi.stats(),
        {
          apply: response => { userStats.value = response },
          onError: () => { userStats.value = null },
        },
      ),
    ])
  }

  async function updateUserKey() {
    const item = editingUserKey.value
    if (!item) return
    const nextName = userKeyForm.value.name.trim()
    const nextKey = userKeyForm.value.key.trim()
    const updates: { name?: string; key?: string } = {}
    if (nextName !== item.name) updates.name = nextName
    if (nextKey) updates.key = nextKey
    if (!Object.keys(updates).length) {
      closeUserKeyModal()
      return
    }

    userKeyBusy.value = item.id
    try {
      const response = await userKeysApi.update(item.id, updates)
      upsertUserKey(response.item)
      toast.success(nextKey ? '用户密钥已更新' : '用户名称已更新')
      userKeyModal.value = ''
      resetUserKeyForm()
    } catch (error) {
      toast.error(errorMessage(error, '更新用户密钥失败'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  async function adjustDailyImages(userIds: string[], count: number, provider: 'gpt' | 'grok' = 'gpt') {
    if (!userIds.length) return
    userKeyBusy.value = 'bulk-daily-image'
    try {
      const response = await userKeysApi.adjustDailyImages(userIds, count, provider)
      response.items.forEach(upsertUserKey)
      toast.success(`已为 ${response.items.length} 位用户增加今日 ${response.count} 次${provider === 'grok' ? 'Grok ' : ''}额度`)
    } catch (error) {
      toast.error(errorMessage(error, '调整今日生图额度失败'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  async function toggleUserKey(item: UserKey) {
    userKeyBusy.value = item.id
    try {
      const response = await userKeysApi.update(item.id, { enabled: !item.enabled })
      upsertUserKey(response.item)
      toast.success(item.enabled ? '用户密钥已禁用' : '用户密钥已启用')
    } catch (error) {
      toast.error(errorMessage(error, '更新用户密钥失败'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  async function deleteUserKey(item: UserKey) {
    const confirmed = await confirmDialog.ask({
      title: '删除用户密钥',
      message: `确定删除用户密钥「${item.name || item.id}」吗？删除后这条密钥将无法继续调用接口。`,
      confirmText: '删除',
      cancelText: '取消',
    })
    if (!confirmed) return

    userKeyBusy.value = item.id
    try {
      const response = await userKeysApi.delete(item.id)
      userKeys.value = userKeys.value.filter(candidate => candidate.id !== response.deleted_id)
      if (editingUserKey.value?.id === item.id) {
        userKeyModal.value = ''
        resetUserKeyForm()
      }
      await userKeysQuery.load()
      toast.success('用户密钥已删除')
    } catch (error) {
      toast.error(errorMessage(error, '删除用户密钥失败'))
    } finally {
      userKeyBusy.value = ''
    }
  }

  function invalidate() {
    userKeysQuery.invalidate()
    userStatsQuery.invalidate()
    userKeysLoaded.value = false
  }

  return {
    userKeys,
    userSearch,
    currentPage: userKeysQuery.currentPage,
    pageSize,
    registrationSource,
    pageSizeOptions: [5, 10, 20, 50, 100],
    userKeysTotal: userKeysQuery.total,
    userStats,
    userKeysLoaded,
    userKeysLoading,
    userKeyBusy,
    userKeyModal,
    editingUserKey,
    userKeyForm,
    resetUserKeyForm,
    openUserKeyEditModal,
    closeUserKeyModal,
    loadUserKeys,
    updateUserKey,
    adjustDailyImages,
    toggleUserKey,
    deleteUserKey,
    invalidate,
  }
}
