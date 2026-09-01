<template>
  <div class="space-y-4">
    <FormSection title="Grok 图片生成" subtitle="仅向符合条件的 Linux.do 普通用户和超级管理员开放，额度与 GPT 图片额度分开计算。">
      <Checkbox v-model="settings.grok_image.enabled" :disabled="fieldReadOnly('grok_image.enabled')">
        开启 Grok 图片生成
      </Checkbox>
      <div class="grid gap-3 md:grid-cols-2">
        <FormField label="Grok API Key">
          <Input
            v-model="settings.grok_image.api_key"
            type="password"
            block
            :disabled="fieldReadOnly('grok_image.api_key')"
            :placeholder="settings.grok_image.has_api_key ? '已配置，留空不修改' : '输入 x.ai API Key'"
          />
        </FormField>
        <FormField label="Base URL">
          <Input v-model.trim="settings.grok_image.base_url" block :disabled="fieldReadOnly('grok_image.base_url')" />
          <p class="mt-1 text-xs text-muted-foreground">请输入完整的 HTTP(S) 地址，例如 https://api.x.ai/v1，不要填写本服务容器地址。</p>
        </FormField>
        <FormField label="Linux.do 用户数">
          <Input v-model.number="settings.grok_image.linuxdo_user_limit" type="number" block :disabled="fieldReadOnly('grok_image.linuxdo_user_limit')" />
        </FormField>
        <FormField label="每日 Grok 上限">
          <Input v-model.number="settings.grok_image.daily_image_limit" type="number" min="2" max="10" block :disabled="fieldReadOnly('grok_image.daily_image_limit')" />
        </FormField>
      </div>
      <p class="text-xs text-muted-foreground">用户数填 0 表示全部 Linux.do 用户；每日上限范围为 2 到 10，系统会按活跃用户动态收紧。</p>
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
