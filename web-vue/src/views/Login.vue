<template>
  <main class="min-h-screen bg-background px-4 py-8 sm:px-6">
    <div class="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-md items-center">
      <section class="w-full rounded-lg border border-border bg-card p-6 shadow-sm sm:p-8">
        <header class="text-center">
          <h1 class="text-2xl font-semibold text-foreground">ChatGPT2API</h1>
          <p class="mt-2 text-sm text-muted-foreground">
            {{ mode === 'register' ? '创建生图用户账号' : mode === 'admin' ? '管理员控制台登录' : '用户登录' }}
          </p>
        </header>

        <ConsoleSegmentedTabs
          v-model="mode"
          class="mt-6"
          :options="authModes"
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
import { computed, reactive, ref } from 'vue'
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
  if (!canRegister.value) return
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
