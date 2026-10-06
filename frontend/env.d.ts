/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AI_CHAT_ENDPOINT?: string
  readonly VITE_KSUSER_AUTH_BASE?: string
  readonly VITE_KSUSER_API_BASE?: string
  readonly VITE_KSUSER_AUTHORIZE_ENDPOINT?: string
  readonly VITE_KSUSER_TOKEN_ENDPOINT?: string
  readonly VITE_KSUSER_USERINFO_ENDPOINT?: string
  readonly VITE_KSUSER_OPENID_CONFIGURATION_ENDPOINT?: string
  readonly VITE_KSUSER_CLIENT_ID?: string
  readonly VITE_KSUSER_CLIENT_SECRET?: string
  readonly VITE_KSUSER_SCOPE?: string
  readonly VITE_KSUSER_REDIRECT_URI?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
