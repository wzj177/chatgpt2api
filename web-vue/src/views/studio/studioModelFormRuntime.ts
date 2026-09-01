import { computed, reactive, ref, watch } from 'vue'
import {
  DEFAULT_IMAGE_MODEL,
  DEFAULT_IMAGE_QUALITY,
  DEFAULT_IMAGE_SIZE,
  createGrokImageSize,
  isImageSizeSupportedByModel,
  isGrokImageModel,
} from '@/api/imageTasks'
import { useModelCatalog } from '@/composables/useModelCatalog'
import {
  getStringPreference,
  preferenceKeys,
  setStringPreference,
} from '@/lib/preferences'
import type { StudioImageForm } from '@/components/studio/types'

export function useStudioModelFormRuntime() {
  const { catalog, chatModels, imageModels, loadModelCatalog } = useModelCatalog()
  const chatModel = ref(getStringPreference(preferenceKeys.studioChatModel, 'auto') || 'auto')
  const chatReasoningEffort = ref(getStringPreference(preferenceKeys.studioChatReasoningEffort, ''))
  const imageForm = reactive<StudioImageForm>({
    model: getStringPreference(preferenceKeys.studioImageModel, DEFAULT_IMAGE_MODEL) || DEFAULT_IMAGE_MODEL,
    size: DEFAULT_IMAGE_SIZE,
    quality: DEFAULT_IMAGE_QUALITY,
    n: 1,
  })
  const providerForms: Record<'gpt' | 'grok', Omit<StudioImageForm, 'model'>> = {
    gpt: {
      size: DEFAULT_IMAGE_SIZE,
      quality: DEFAULT_IMAGE_QUALITY,
      n: 1,
    },
    grok: {
      size: createGrokImageSize('1k', '1:1'),
      quality: 'medium',
      n: 1,
    },
  }

  const chatModelOptions = computed(() => (
    catalog.value ? [...chatModels.value] : uniqueStrings([chatModel.value])
  ))
  const imageModelOptions = computed(() => (
    catalog.value ? [...imageModels.value] : uniqueStrings([imageForm.model])
  ))
  const imageHighResolutionEnabled = computed(() => {
    const capabilities = catalog.value?.capabilities
    return Boolean(
      capabilities?.image_upscale
      || capabilities?.high_resolution_image_models.includes(imageForm.model),
    )
  })

  watch(chatModel, (model) => setStringPreference(preferenceKeys.studioChatModel, model || 'auto'))
  watch(chatReasoningEffort, (effort) => setStringPreference(preferenceKeys.studioChatReasoningEffort, effort || ''))
  watch(() => imageForm.model, (model) => {
    setStringPreference(preferenceKeys.studioImageModel, model || DEFAULT_IMAGE_MODEL)
  })
  watch(() => imageForm.model, (model, previousModel) => {
    if (!previousModel) return
    const previousProvider = isGrokImageModel(previousModel) ? 'grok' : 'gpt'
    const nextProvider = isGrokImageModel(model) ? 'grok' : 'gpt'
    if (previousProvider === nextProvider) return
    providerForms[previousProvider] = {
      size: imageForm.size,
      quality: imageForm.quality,
      n: imageForm.n,
    }
    Object.assign(imageForm, providerForms[nextProvider])
  })
  watch(catalog, (value) => {
    if (!value) return
    if (!value.chat_models.includes(chatModel.value)) {
      chatModel.value = value.defaults.chat_model
    }
    if (!value.image_models.includes(imageForm.model)) {
      imageForm.model = value.defaults.image_model
    }
  }, { immediate: true })
  watch([() => imageForm.model, imageHighResolutionEnabled], ([, highResolutionEnabled]) => {
    if (isGrokImageModel(imageForm.model)) {
      if (!['low', 'medium'].includes(imageForm.quality)) imageForm.quality = 'medium'
      if (!/^grok:(1k|2k):(1:1|16:9|9:16|4:3|3:4|3:2|2:3)$/.test(imageForm.size)) {
        imageForm.size = createGrokImageSize('1k', '1:1')
      }
      imageForm.n = 1
      return
    }
    if (!isImageSizeSupportedByModel(imageForm.size, highResolutionEnabled)) imageForm.size = DEFAULT_IMAGE_SIZE
  }, { immediate: true })

  return {
    chatModel,
    chatModelOptions,
    chatReasoningEffort,
    imageForm,
    imageModelOptions,
    imageHighResolutionEnabled,
    loadModelCatalog,
  }
}

function uniqueStrings(values: string[]) {
  return values.map((value) => String(value || '').trim()).filter((value, index, arr) => value && arr.indexOf(value) === index)
}
