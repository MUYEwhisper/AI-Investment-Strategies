<script setup lang="ts">
import { computed } from 'vue'
import type { AccountSession } from '../services/account'
import type { KsuserSession } from '../services/ksuser-auth'

const props = defineProps<{
  session: KsuserSession
  sessions: AccountSession[]
  busy: boolean
  errorMessage: string
}>()

const emit = defineEmits<{
  signOut: []
  revokeCurrent: []
  revokeOthers: []
  refreshSessions: []
}>()

const displayName = computed(
  () => props.session.profile.nickname || props.session.profile.email || 'Ksuser 用户',
)

const expiresAtText = computed(() =>
  new Date(props.session.expiresAt).toLocaleString('zh-CN', {
    hour12: false,
  }),
)

</script>

<template>
  <section class="account-shell">
    <article class="panel account-hero" id="accountCenterPanel">
      <div class="account-identity">
        <img
          v-if="session.profile.avatar_url"
          :src="session.profile.avatar_url"
          :alt="`${displayName} avatar`"
          class="account-avatar"
        />
        <div v-else class="account-avatar account-avatar-fallback">{{ displayName.slice(0, 1) }}</div>

        <div class="account-copy">
          <div class="account-kicker">Ksuser 当前登录用户</div>
          <h2>{{ displayName }}</h2>
          <p>{{ session.profile.email || '当前账号未返回 email 信息。' }}</p>
        </div>
      </div>

      <div class="account-actions">
        <RouterLink class="btn" to="/">回到市场总览</RouterLink>
        <button class="btn primary" type="button" @click="emit('signOut')">退出登录</button>
      </div>
    </article>

    <div class="account-grid">
      <article class="panel account-card">
        <div class="panel-title">授权范围</div>
        <dl class="account-info">
          <div>
            <dt>已授权 Scope</dt>
            <dd>{{ session.scopeText }}</dd>
          </div>
        </dl>
      </article>

      <article class="panel account-card">
        <div class="panel-title">会话状态</div>
        <dl class="account-info">
          <div>
            <dt>过期时间</dt>
            <dd>{{ expiresAtText }}</dd>
          </div>
        </dl>
      </article>
    </div>

    <article class="panel account-card">
      <div class="account-session-head">
        <div class="panel-title">登录会话管理</div>
        <div class="account-session-actions">
          <button class="btn" type="button" :disabled="busy" @click="emit('refreshSessions')">刷新会话</button>
          <button class="btn" type="button" :disabled="busy" @click="emit('revokeOthers')">撤销其他设备</button>
          <button class="btn primary" type="button" :disabled="busy" @click="emit('revokeCurrent')">撤销当前设备</button>
        </div>
      </div>

      <p v-if="errorMessage" class="account-error">{{ errorMessage }}</p>

      <div v-if="sessions.length" class="account-session-list">
        <div v-for="item in sessions" :key="item.id" class="account-session-item">
          <div class="account-session-line">
            <strong>{{ item.isCurrent ? '当前设备' : '其他设备' }}</strong>
            <span>{{ item.ip || 'unknown-ip' }}</span>
          </div>
          <div class="account-session-line">
            <span>创建: {{ item.createdAt }}</span>
            <span>最近访问: {{ item.lastSeenAt }}</span>
            <span>到期: {{ item.expiresAt }}</span>
          </div>
          <div class="account-session-agent">{{ item.userAgent || 'unknown-user-agent' }}</div>
        </div>
      </div>
      <div v-else class="account-session-empty">暂无会话信息</div>
    </article>
  </section>
</template>

<style scoped>
.account-shell {
  display: grid;
  gap: 14px;
}

.account-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 24px;
  border-radius: 28px;
}

.account-identity {
  display: flex;
  align-items: center;
  gap: 16px;
}

.account-avatar {
  width: 72px;
  height: 72px;
  border-radius: 24px;
  object-fit: cover;
  box-shadow: 0 12px 24px rgba(15, 61, 99, 0.12);
}

.account-avatar-fallback {
  display: grid;
  place-items: center;
  font-size: 28px;
  font-weight: 800;
  color: #ffffff;
  background: linear-gradient(160deg, #0ea5e9, #2563eb);
}

.account-copy {
  display: grid;
  gap: 6px;
}

.account-kicker {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent-deep);
}

.account-copy h2 {
  font-size: clamp(26px, 4vw, 36px);
  line-height: 1.06;
}

.account-copy p {
  color: var(--sub);
}

.account-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.account-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.account-card {
  padding: 22px;
}

.account-info {
  display: grid;
  gap: 14px;
  margin-top: 16px;
}

.account-info div {
  display: grid;
  gap: 6px;
  padding-bottom: 14px;
  border-bottom: 1px dashed rgba(14, 165, 233, 0.18);
}

.account-info div:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.account-info dt {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--sub);
}

.account-info dd {
  overflow-wrap: anywhere;
  color: var(--ink);
}

.account-session-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.account-session-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.account-session-list {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.account-session-item {
  border: 1px solid rgba(14, 165, 233, 0.18);
  border-radius: 14px;
  padding: 12px;
  display: grid;
  gap: 6px;
}

.account-session-line {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--sub);
  font-size: 13px;
}

.account-session-agent {
  font-size: 12px;
  color: var(--sub);
  overflow-wrap: anywhere;
}

.account-session-empty {
  margin-top: 12px;
  color: var(--sub);
}

.account-error {
  margin-top: 12px;
  color: #dc2626;
  font-size: 13px;
}

@media (max-width: 960px) {
  .account-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .account-grid {
    grid-template-columns: 1fr;
  }
}
</style>
