<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

type SignInDraft = {
  clientId: string
  clientSecret: string
  redirectUri: string
  scopeText: string
}

const props = defineProps<{
  busy: boolean
  configured: boolean
  errorMessage: string
  clientId: string
  clientSecret: string
  redirectUri: string
  scope: string[]
  authorizeEndpoint: string
  dialogReason: string
  registerUrl: string
  showClose?: boolean
}>()

const emit = defineEmits<{
  signIn: [payload: SignInDraft]
  close: []
}>()

const form = reactive<SignInDraft>({
  clientId: props.clientId,
  clientSecret: props.clientSecret,
  redirectUri: props.redirectUri,
  scopeText: props.scope.join(' '),
})

const clientIdPreview = computed(() => {
  const value = form.clientId.trim()
  if (!value) return '未配置 AppID'
  if (value.length <= 12) return value
  return `${value.slice(0, 6)}...${value.slice(-4)}`
})

watch(
  () => [props.clientId, props.clientSecret, props.redirectUri, props.scope.join(' ')] as const,
  ([clientId, clientSecret, redirectUri, scopeText]) => {
    form.clientId = clientId
    form.clientSecret = clientSecret
    form.redirectUri = redirectUri
    form.scopeText = scopeText
  },
)

function submit(): void {
  emit('signIn', {
    clientId: form.clientId.trim(),
    clientSecret: form.clientSecret.trim(),
    redirectUri: form.redirectUri.trim(),
    scopeText: form.scopeText.trim(),
  })
}
</script>

<template>
  <section class="signin-shell" id="signInPanel">
    <article class="signin-rail">
      <div class="signin-brand-pill">
        <span class="signin-brand-mark">K</span>
        <strong>Ksuser 登录</strong>
      </div>

      <div class="signin-copy">
        <div class="signin-kicker">Secure Access</div>
        <h2>开始登录</h2>
        <p>{{ dialogReason }}</p>
      </div>

      <div class="signin-points">
        <div class="signin-point">同步自选股与历史会话</div>
        <div class="signin-point">完成认证后返回当前工作区</div>
      </div>

      <div class="signin-meta">
        <div class="signin-ready" :class="{ ready: configured }">
          {{ configured ? '应用已准备就绪' : '等待填写 AppID' }}
        </div>
        <div class="signin-side-meta">当前应用：{{ clientIdPreview }}</div>
      </div>
    </article>

    <form class="signin-card" @submit.prevent="submit">
      <button
        v-if="showClose"
        class="signin-close"
        type="button"
        aria-label="关闭登录弹窗"
        @click="$emit('close')"
      >
        ×
      </button>

      <div class="signin-card-head">
        <div class="signin-card-kicker">KSUSER ACCOUNT</div>
        <h3>继续登录智能投研工作台</h3>
        <p>前往 Ksuser 完成认证后，将自动返回当前页面。</p>
      </div>

      <div class="signin-status-row">
        <span class="signin-status-label">回调地址</span>
        <code>{{ redirectUri }}</code>
      </div>

      <button class="signin-submit" type="submit" :disabled="busy">
        {{ busy ? '正在前往 Ksuser...' : '下一步' }}
      </button>

      <div class="signin-register-row">
        <span>还没有账号？</span>
        <a :href="registerUrl" target="_blank" rel="noreferrer">创建账号</a>
      </div>

      <p v-if="errorMessage" class="signin-error">{{ errorMessage }}</p>
      <p v-else class="signin-hint">若登录失败，请确认 Ksuser 平台登记的回调地址与当前配置一致。</p>

      <details class="signin-details">
        <summary>{{ configured ? '查看高级配置' : '填写高级配置' }}</summary>

        <div class="signin-form">
          <label class="signin-field">
            <span>Ksuser AppID</span>
            <input v-model="form.clientId" type="text" autocomplete="off" placeholder="请输入团队提供的 AppID" />
          </label>

          <label class="signin-field">
            <span>AppSecret</span>
            <input
              v-model="form.clientSecret"
              type="password"
              autocomplete="off"
              placeholder="如平台要求 AppSecret，请填写在此"
            />
          </label>

          <label class="signin-field">
            <span>回调地址</span>
            <input v-model="form.redirectUri" type="text" autocomplete="off" />
          </label>

          <label class="signin-field">
            <span>授权范围</span>
            <input v-model="form.scopeText" type="text" autocomplete="off" placeholder="openid profile email" />
          </label>
        </div>

        <div class="signin-detail-note">
          <span>授权入口</span>
          <code>{{ authorizeEndpoint }}</code>
        </div>
      </details>
    </form>
  </section>
</template>

<style scoped>
.signin-shell {
  display: grid;
  grid-template-columns: minmax(300px, 0.82fr) minmax(420px, 1fr);
  min-height: min(640px, calc(100vh - 48px));
  border-radius: 30px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background:
    radial-gradient(circle at top left, rgba(255, 191, 73, 0.12), transparent 26%),
    linear-gradient(135deg, rgba(16, 17, 22, 0.97), rgba(10, 11, 15, 0.99));
  box-shadow:
    0 40px 90px rgba(0, 0, 0, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.signin-rail {
  display: grid;
  align-content: space-between;
  gap: 24px;
  padding: 38px 34px 30px;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  background:
    radial-gradient(circle at top left, rgba(255, 204, 97, 0.14), transparent 24%),
    linear-gradient(180deg, rgba(28, 29, 34, 0.98), rgba(21, 22, 27, 0.96));
}

.signin-brand-pill {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  width: fit-content;
  padding: 10px 18px 10px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #f5f7fb;
}

.signin-brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: linear-gradient(135deg, #ffc241, #ffb100);
  color: #221707;
  font-weight: 900;
}

.signin-copy {
  display: grid;
  gap: 12px;
}

.signin-kicker {
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(255, 192, 84, 0.9);
}

.signin-copy h2 {
  font-size: clamp(42px, 5vw, 56px);
  line-height: 1.02;
  color: #f7f8fa;
}

.signin-copy p {
  max-width: 360px;
  font-size: 15px;
  line-height: 1.8;
  color: rgba(214, 219, 229, 0.82);
}

.signin-points {
  display: grid;
  gap: 12px;
}

.signin-point {
  padding: 15px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: rgba(245, 247, 251, 0.88);
  font-size: 14px;
  line-height: 1.6;
}

.signin-meta {
  display: grid;
  gap: 10px;
}

.signin-ready {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 9px 14px;
  border-radius: 999px;
  background: rgba(255, 107, 92, 0.14);
  color: #ffbbb2;
  font-size: 12px;
  font-weight: 700;
}

.signin-ready.ready {
  background: rgba(255, 193, 71, 0.16);
  color: #ffd36d;
}

.signin-side-meta {
  color: rgba(196, 203, 214, 0.72);
  font-size: 12px;
}

.signin-card {
  position: relative;
  display: grid;
  align-content: start;
  gap: 18px;
  padding: 38px 34px 30px;
  background:
    radial-gradient(circle at top right, rgba(255, 192, 74, 0.1), transparent 30%),
    linear-gradient(180deg, rgba(12, 13, 17, 0.98), rgba(9, 10, 14, 0.99));
  color: #f5f7fb;
}

.signin-close {
  position: absolute;
  top: 18px;
  right: 18px;
  width: 38px;
  height: 38px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(243, 246, 251, 0.9);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  transition:
    background 0.18s ease,
    transform 0.18s ease,
    border-color 0.18s ease;
}

.signin-close:hover {
  transform: translateY(-1px);
  border-color: rgba(255, 196, 84, 0.34);
  background: rgba(255, 255, 255, 0.08);
}

.signin-card-head {
  display: grid;
  gap: 10px;
  padding-right: 54px;
}

.signin-card-kicker {
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(255, 192, 84, 0.9);
}

.signin-card-head h3 {
  font-size: clamp(30px, 4vw, 46px);
  line-height: 1.08;
}

.signin-card-head p {
  max-width: 420px;
  font-size: 15px;
  line-height: 1.75;
  color: rgba(215, 221, 230, 0.78);
}

.signin-status-row {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.signin-status-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(210, 217, 227, 0.7);
}

.signin-status-row code,
.signin-detail-note code {
  overflow-wrap: anywhere;
  color: #ffe1a0;
  font-size: 12px;
}

.signin-submit {
  width: 100%;
  min-height: 56px;
  border: 0;
  border-radius: 18px;
  background: linear-gradient(135deg, #ffc743, #ffb300);
  color: #1a1407;
  font-size: 19px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 18px 36px rgba(255, 179, 0, 0.22);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    filter 0.18s ease;
}

.signin-submit:hover {
  transform: translateY(-1px);
  filter: brightness(1.03);
  box-shadow: 0 22px 42px rgba(255, 179, 0, 0.28);
}

.signin-submit:disabled {
  opacity: 0.7;
  cursor: wait;
  transform: none;
  box-shadow: none;
}

.signin-register-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  color: rgba(215, 221, 230, 0.74);
}

.signin-register-row a {
  color: #ffc743;
  text-decoration: none;
  font-weight: 700;
}

.signin-register-row a:hover {
  text-decoration: underline;
}

.signin-error {
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 107, 92, 0.12);
  border: 1px solid rgba(255, 136, 121, 0.2);
  color: #ffbeb5;
  font-size: 13px;
  line-height: 1.7;
}

.signin-hint {
  font-size: 13px;
  line-height: 1.75;
  color: rgba(215, 221, 230, 0.72);
}

.signin-details {
  display: grid;
  gap: 14px;
  padding-top: 2px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.signin-details summary {
  padding-top: 14px;
  cursor: pointer;
  color: rgba(247, 248, 250, 0.92);
  font-size: 13px;
  font-weight: 700;
}

.signin-form {
  display: grid;
  gap: 12px;
}

.signin-field {
  display: grid;
  gap: 8px;
}

.signin-field span {
  color: rgba(202, 209, 218, 0.78);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.signin-field input {
  width: 100%;
  min-height: 52px;
  padding: 0 16px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.06);
  color: #f7f8fa;
  font-size: 14px;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.signin-field input::placeholder {
  color: rgba(190, 198, 208, 0.46);
}

.signin-field input:focus {
  outline: none;
  transform: translateY(-1px);
  border-color: rgba(255, 196, 84, 0.38);
  box-shadow: 0 0 0 4px rgba(255, 196, 84, 0.12);
}

.signin-detail-note {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.signin-detail-note span {
  font-size: 12px;
  color: rgba(202, 209, 218, 0.72);
}

@media (max-width: 940px) {
  .signin-shell {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .signin-rail {
    border-right: 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
}

@media (max-width: 640px) {
  .signin-rail,
  .signin-card {
    padding: 26px 20px 22px;
  }

  .signin-card-head {
    padding-right: 44px;
  }

  .signin-card-head h3,
  .signin-copy h2 {
    font-size: 34px;
  }

  .signin-register-row {
    flex-wrap: wrap;
  }
}
</style>
