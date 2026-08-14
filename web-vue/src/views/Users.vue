<template>
  <div class="space-y-6">
    <PagePanel class="users-page-panel space-y-5">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="ui-section-title">用户管理</p>
          <p class="mt-1 text-xs text-muted-foreground">管理注册用户、登录状态和成功生图用量。</p>
        </div>
      </div>

      <SettingsUserKeysPanel
        :user-keys="userKeys"
        :user-stats="userStats"
        :user-keys-loading="userKeysLoading"
        :user-key-busy="userKeyBusy"
        @load="loadUserKeys"
        @edit="openUserKeyEditModal"
        @toggle="toggleUserKey"
        @delete="deleteUserKey"
      />
    </PagePanel>

    <SettingsUserKeyModals
      :modal="userKeyModal"
      :form="userKeyForm"
      :editing-user-key="editingUserKey"
      :busy="userKeyBusy"
      @close="closeUserKeyModal"
      @update="updateUserKey"
    />
  </div>
</template>

<script setup lang="ts">
import PagePanel from '@/components/ai/PagePanel.vue'
import SettingsUserKeyModals from '@/views/settings/SettingsUserKeyModals.vue'
import SettingsUserKeysPanel from '@/views/settings/SettingsUserKeysPanel.vue'
import { usePageRuntime } from '@/composables/usePageRuntime'
import { useSettingsUserKeysRuntime } from '@/views/settings/settingsUserKeysRuntime'

defineOptions({ name: 'Users' })

const pageRuntime = usePageRuntime('users')
const userKeysRuntime = useSettingsUserKeysRuntime({
  runtime: pageRuntime,
  requestKey: 'users:list',
})

const userKeys = userKeysRuntime.userKeys
const userStats = userKeysRuntime.userStats
const userKeysLoading = userKeysRuntime.userKeysLoading
const userKeyBusy = userKeysRuntime.userKeyBusy
const userKeyModal = userKeysRuntime.userKeyModal
const editingUserKey = userKeysRuntime.editingUserKey
const userKeyForm = userKeysRuntime.userKeyForm
const openUserKeyEditModal = userKeysRuntime.openUserKeyEditModal
const closeUserKeyModal = userKeysRuntime.closeUserKeyModal
const loadUserKeys = userKeysRuntime.loadUserKeys
const updateUserKey = userKeysRuntime.updateUserKey
const toggleUserKey = userKeysRuntime.toggleUserKey
const deleteUserKey = userKeysRuntime.deleteUserKey

pageRuntime.onActivate(() => {
  if (!userKeysRuntime.userKeysLoaded.value) void loadUserKeys()
})
</script>

<style scoped>
.users-page-panel {
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0;
}
</style>
