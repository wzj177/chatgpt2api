<template>
  <main class="min-h-screen bg-background px-4 py-8 sm:px-6">
    <div class="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-md items-center">
      <section class="w-full rounded-lg border border-border bg-card p-6 shadow-sm sm:p-8">
        <header class="text-center">
          <h1 class="text-2xl font-semibold text-foreground">丸子生图</h1>
          <p class="mt-2 text-sm text-muted-foreground">
            {{ mode === 'register' ? '创建生图用户账号' : mode === 'admin' ? '管理员控制台登录' : '用户登录' }}
          </p>
        </header>

        <ConsoleSegmentedTabs
          v-model="mode"
          class="mt-6"
          :options="visibleAuthModes"
          aria-label="登录方式"
        />

        <form v-if="mode === 'user'" class="mt-6 space-y-4" @submit.prevent="handleUserLogin">
          <FormField label="邮箱">
            <Input v-model.trim="loginForm.email" type="email" block autocomplete="email" placeholder="name@example.com" :disabled="isLoading" />
          </FormField>
          <FormField label="密码">
            <Input v-model="loginForm.password" type="password" block autocomplete="current-password" placeholder="输入密码" :disabled="isLoading" />
          </FormField>
          <TermsConsent v-model="loginForm.accepted" :disabled="isLoading" @open="openProtocol" />
          <Button type="submit" size="md" variant="primary" block :disabled="isLoading || !canUserLogin">
            {{ isLoading ? '登录中...' : '登录' }}
          </Button>
          <template v-if="linuxdoEnabled">
            <div class="flex items-center gap-3 text-xs text-muted-foreground">
              <span class="h-px flex-1 bg-border"></span>
              <span>或</span>
              <span class="h-px flex-1 bg-border"></span>
            </div>
            <Button
              type="button"
              size="md"
              variant="outline"
              block
              :disabled="isLoading || !loginForm.accepted"
              @click="handleLinuxDoLogin"
            >
              <img src="/oauth-assets/linuxdo.png" alt="" class="mr-2 h-4 w-4" />
              使用 Linux.do 登录
            </Button>
          </template>
        </form>

        <form v-else-if="mode === 'register'" class="mt-6 space-y-4" @submit.prevent="handleRegister">
          <div class="grid gap-4 sm:grid-cols-2">
            <FormField label="用户名">
              <Input v-model.trim="registerForm.username" block autocomplete="username" placeholder="怎么称呼你" :disabled="isLoading" />
            </FormField>
            <FormField label="手机号（可选）">
              <Input v-model.trim="registerForm.phone" type="tel" block autocomplete="tel" placeholder="用于后续通知" :disabled="isLoading" />
            </FormField>
          </div>
          <FormField label="邮箱">
            <Input v-model.trim="registerForm.email" type="email" block autocomplete="email" placeholder="name@example.com" :disabled="isLoading" />
          </FormField>
          <div class="grid gap-4 sm:grid-cols-2">
            <FormField label="密码">
              <Input v-model="registerForm.password" type="password" block autocomplete="new-password" placeholder="至少 8 位" :disabled="isLoading" />
            </FormField>
            <FormField label="确认密码">
              <Input v-model="registerForm.passwordConfirmation" type="password" block autocomplete="new-password" placeholder="再次输入密码" :disabled="isLoading" />
            </FormField>
          </div>
          <p v-if="passwordMismatch" class="text-xs text-rose-600">两次密码输入不一致。</p>
          <TermsConsent v-model="registerForm.accepted" :disabled="isLoading" @open="openProtocol" />
          <Button type="submit" size="md" variant="primary" block :disabled="isLoading || !canRegister">
            {{ isLoading ? '注册中...' : '注册并登录' }}
          </Button>
        </form>

        <form v-else class="mt-6 space-y-4" @submit.prevent="handleAdminLogin">
          <FormField label="管理员密钥">
            <Input v-model="adminKey" type="password" block autocomplete="current-password" placeholder="输入 CHATGPT2API_AUTH_KEY" :disabled="isLoading" />
          </FormField>
          <TermsConsent v-model="adminAccepted" :disabled="isLoading" @open="openProtocol" />
          <Button type="submit" size="md" variant="primary" block :disabled="isLoading || !adminKey || !adminAccepted">
            {{ isLoading ? '登录中...' : '进入管理后台' }}
          </Button>
        </form>
      </section>
    </div>

    <ModalShell
      :open="protocolOpen"
      max-width="min(42rem, calc(100vw - 2rem))"
      scrollable
      close-on-backdrop
      aria-label="用户协议"
      @close="protocolOpen = false"
    >
      <ModalHeader title="用户协议" subtitle="登录或注册前请阅读并确认" @close="protocolOpen = false" />
      <ModalBody>
        <PageLoadingState v-if="protocolLoading" compact title="正在加载协议" description="读取当前服务协议。" />
        <StateBlock v-else-if="protocolError" compact :description="protocolError">
          <Button size="sm" variant="outline" root-class="mt-4" @click="loadProtocol">重新加载</Button>
        </StateBlock>
        <StudioMarkdownContent v-else :content="protocolMarkdown" />
      </ModalBody>
    </ModalShell>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, FormField, Input } from 'nanocat-ui'
import type { SegmentedValue } from 'nanocat-ui'
import { authApi } from '@/api/auth'
import ConsoleSegmentedTabs from '@/components/ai/ConsoleSegmentedTabs.vue'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import StudioMarkdownContent from '@/components/studio/StudioMarkdownContent.vue'
import TermsConsent from '@/components/auth/TermsConsent.vue'
import { useToast } from '@/composables/useToast'
import { errorMessage } from '@/lib/errorMessage'
import { resolveLoginRedirect } from '@/router/routes'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const toast = useToast()

const mode = ref<SegmentedValue>('user')
const isLoading = ref(false)
const adminKey = ref('')
const adminAccepted = ref(false)
const protocolOpen = ref(false)
const protocolLoading = ref(false)
const protocolMarkdown = ref('')
const protocolError = ref('')
const linuxdoEnabled = ref(false)
const registrationEnabled = ref(true)

const loginForm = reactive({ email: '', password: '', accepted: false })
const registerForm = reactive({
  email: '',
  password: '',
  passwordConfirmation: '',
  username: '',
  phone: '',
  accepted: false,
})

const authModes = [
  { value: 'user', label: '用户登录' },
  { value: 'register', label: '注册' },
  { value: 'admin', label: '管理员' },
]
const visibleAuthModes = computed(() => registrationEnabled.value
  ? authModes
  : authModes.filter(item => item.value !== 'register'))

const passwordMismatch = computed(() => (
  Boolean(registerForm.passwordConfirmation) && registerForm.password !== registerForm.passwordConfirmation
))
const canUserLogin = computed(() => Boolean(loginForm.email && loginForm.password && loginForm.accepted))
const canRegister = computed(() => Boolean(
  registerForm.email
  && registerForm.username
  && registerForm.password.length >= 8
  && registerForm.password === registerForm.passwordConfirmation
  && registerForm.accepted
))

async function finishLogin(authenticated: boolean) {
  if (!authenticated) {
    toast.error('登录信息无效或账号已停用。')
    return
  }
  await router.replace(resolveLoginRedirect(route.query.redirect, authStore.homeRoute))
}

async function handleUserLogin() {
  if (!canUserLogin.value) return
  isLoading.value = true
  try {
    await finishLogin(await authStore.passwordLogin(loginForm.email, loginForm.password))
  } catch (error) {
    toast.error(errorMessage(error, '登录失败，请检查邮箱和密码。'))
  } finally {
    isLoading.value = false
  }
}

async function handleRegister() {
  if (!registrationEnabled.value || !canRegister.value) return
  isLoading.value = true
  try {
    await finishLogin(await authStore.register({
      email: registerForm.email,
      password: registerForm.password,
      password_confirmation: registerForm.passwordConfirmation,
      username: registerForm.username,
      phone: registerForm.phone,
      accepted_terms: registerForm.accepted,
    }))
  } catch (error) {
    toast.error(errorMessage(error, '注册失败，请检查填写内容。'))
  } finally {
    isLoading.value = false
  }
}

async function handleAdminLogin() {
  if (!adminKey.value || !adminAccepted.value) return
  isLoading.value = true
  try {
    await finishLogin(await authStore.login(adminKey.value))
  } catch (error) {
    toast.error(errorMessage(error, '管理员密钥无效。'))
  } finally {
    isLoading.value = false
  }
}

async function handleLinuxDoLogin() {
  if (!loginForm.accepted) return
  isLoading.value = true
  try {
    const result = await authApi.linuxdoStart()
    window.location.assign(result.authorization_url)
  } catch (error) {
    toast.error(errorMessage(error, 'Linux.do 登录暂不可用。'))
    isLoading.value = false
  }
}

async function handleLinuxDoCallback() {
  const code = String(route.query.oauth_code || '').trim()
  const oauthError = String(route.query.oauth_error || '').trim()
  if (oauthError) {
    toast.error(oauthError)
    await router.replace({ path: '/login' })
    return
  }
  if (!code) return
  isLoading.value = true
  try {
    await finishLogin(await authStore.linuxdoLogin(code))
  } catch (error) {
    toast.error(errorMessage(error, 'Linux.do 登录失败，请重试。'))
    await router.replace({ path: '/login' })
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  void (async () => {
    try {
      const [linuxdoConfig, registrationConfig] = await Promise.all([
        authApi.linuxdoConfig(),
        authApi.registrationConfig(),
      ])
      linuxdoEnabled.value = linuxdoConfig.enabled
      registrationEnabled.value = registrationConfig.enabled
      if (!registrationEnabled.value && mode.value === 'register') mode.value = 'user'
    } catch {
      linuxdoEnabled.value = false
    }
    await handleLinuxDoCallback()
  })()
})

async function loadProtocol() {
  protocolLoading.value = true
  protocolError.value = ''
  try {
    const result = await authApi.protocol()
    protocolMarkdown.value = result.markdown
  } catch (error) {
    protocolError.value = errorMessage(error, '协议加载失败。')
  } finally {
    protocolLoading.value = false
  }
}

function openProtocol() {
  protocolOpen.value = true
  if (!protocolMarkdown.value && !protocolLoading.value) void loadProtocol()
}
</script>
