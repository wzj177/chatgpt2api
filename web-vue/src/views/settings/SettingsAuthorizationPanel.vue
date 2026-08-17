<template>
  <div class="space-y-4">
    <FormSection
      title="用户注册"
      subtitle="关闭后，前端隐藏注册入口，直接调用注册接口也会返回 403。"
    >
      <Checkbox
        v-model="settings.oauth.registration_enabled"
        :disabled="fieldReadOnly('oauth.registration_enabled')"
      >
        开放用户注册
      </Checkbox>
    </FormSection>

    <FormSection
      title="Linux.do 登录"
      subtitle="仅用于普通用户登录，不会授予管理员控制台权限。"
    >
      <div class="flex items-start gap-3 rounded-md border border-border bg-muted/20 p-3">
        <img src="/oauth-assets/linuxdo.png" alt="Linux.do" class="mt-0.5 h-5 w-5 shrink-0" />
        <div class="min-w-0 flex-1">
          <Checkbox
            v-model="settings.oauth.linuxdo.enabled"
            :disabled="fieldReadOnly('oauth.linuxdo.enabled')"
          >
            开启 Linux.do 登录
          </Checkbox>
          <p class="mt-1 text-xs text-muted-foreground">
            保存后，登录页面的普通用户登录区域会显示 Linux.do 登录入口。
          </p>
        </div>
      </div>

      <div class="grid gap-3 md:grid-cols-2">
        <FormField label="Client ID">
          <Input
            v-model.trim="settings.oauth.linuxdo.client_id"
            block
            :disabled="fieldReadOnly('oauth.linuxdo.client_id')"
            placeholder="输入 Linux.do Client ID"
          />
        </FormField>
        <FormField label="Client Secret">
          <Input
            v-model="settings.oauth.linuxdo.client_secret"
            type="password"
            block
            :disabled="fieldReadOnly('oauth.linuxdo.client_secret')"
            :placeholder="settings.oauth.linuxdo.has_client_secret ? '已配置，留空不修改' : '输入 Linux.do Client Secret'"
          />
        </FormField>
      </div>

      <FormField label="Authorization Endpoint">
        <Input v-model.trim="settings.oauth.linuxdo.authorization_endpoint" block :disabled="fieldReadOnly('oauth.linuxdo.authorization_endpoint')" />
      </FormField>
      <FormField label="Token Endpoint">
        <Input v-model.trim="settings.oauth.linuxdo.token_endpoint" block :disabled="fieldReadOnly('oauth.linuxdo.token_endpoint')" />
      </FormField>
      <FormField label="User Endpoint">
        <Input v-model.trim="settings.oauth.linuxdo.user_endpoint" block :disabled="fieldReadOnly('oauth.linuxdo.user_endpoint')" />
      </FormField>
      <FormField label="OIDC Discovery">
        <Input v-model.trim="settings.oauth.linuxdo.oidc_discovery" block :disabled="fieldReadOnly('oauth.linuxdo.oidc_discovery')" />
      </FormField>
    </FormSection>
  </div>
</template>

<script setup lang="ts">
import { Checkbox, FormField, Input } from 'nanocat-ui'

import FormSection from '@/components/ai/FormSection.vue'
import type { Settings, SettingsFieldMetadata } from '@/types/api'
import { settingsFieldReadOnly } from '@/views/settings/settingsView'

const props = defineProps<{
  settings: Settings
  fields: Record<string, SettingsFieldMetadata>
}>()

function fieldReadOnly(path: string) {
  return settingsFieldReadOnly(props.fields, path)
}
</script>
