<template>
  <Checkbox
    :model-value="modelValue"
    :disabled="disabled"
    @update:model-value="emit('update:modelValue', Boolean($event))"
  >
    <span class="text-sm text-muted-foreground">
      我已阅读并同意
      <button type="button" class="font-medium text-foreground underline underline-offset-4" @click.stop="emit('open')">
        用户协议
      </button>
    </span>
  </Checkbox>
</template>

<script setup lang="ts">
import { Checkbox } from 'nanocat-ui'

withDefaults(defineProps<{
  modelValue: boolean
  disabled?: boolean
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  open: []
}>()
</script>
