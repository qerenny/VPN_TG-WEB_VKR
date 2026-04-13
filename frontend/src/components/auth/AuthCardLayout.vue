<script setup lang="ts">
defineProps<{
  subtitle: string
}>()
</script>

<template>
  <main class="page-shell auth-page">
    <div class="auth-scene" aria-hidden="true">
      <div class="auth-scene__orb auth-scene__orb--one"></div>
      <div class="auth-scene__orb auth-scene__orb--two"></div>
      <div class="auth-scene__ring auth-scene__ring--one"></div>
      <span class="auth-scene__dot auth-scene__dot--one"></span>
      <span class="auth-scene__dot auth-scene__dot--two"></span>
    </div>

    <section class="auth-card glass-card cabinet-panel">
      <div class="auth-logo-wrap">
        <img src="/favicon.svg" alt="Логотип сервиса" class="auth-logo" />
      </div>

      <div class="auth-card__body">
        <h1 class="auth-card__title brand-title">Remote Access</h1>
        <p class="auth-card__subtitle">{{ subtitle }}</p>
        <slot />

        <footer v-if="$slots.footer" class="auth-footer">
          <slot name="footer" />
        </footer>
      </div>
    </section>
  </main>
</template>

<style scoped>
.auth-page {
  display: grid;
  place-items: center;
  padding-top: max(4vh, 24px);
  padding-bottom: max(4vh, 24px);
}

.auth-card {
  width: min(480px, 100%);
  text-align: center;
}

.auth-logo-wrap {
  display: flex;
  justify-content: center;
  margin-bottom: 8px;
}

.auth-logo {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: 3px solid rgba(255, 90, 68, 0.3);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 24px rgba(151, 53, 34, 0.18);
  animation: float-soft 4s ease-in-out infinite;
}

.auth-card__body {
  display: grid;
  gap: 6px;
}

.auth-card__title {
  margin: 0;
  font-size: clamp(32px, 6vw, 44px);
  color: var(--accent);
}

.auth-card__subtitle {
  margin: 0;
  font: 700 14px/1.2 var(--font-ui);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--cabinet-muted, var(--muted));
}

:slotted(.auth-form) {
  display: grid;
  gap: 14px;
  margin-top: 18px;
  text-align: left;
}

:global(.auth-field) {
  display: grid;
  gap: 6px;
}

:global(.auth-field-error) {
  margin: -6px 0 0;
  color: #a73b25;
  font: 700 13px/1.4 var(--font-ui);
}

:global(.auth-submit) {
  width: 100%;
  margin-top: 2px;
}

.auth-footer {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 20px;
  margin-top: 20px;
}

:slotted(.auth-footer__link) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--accent);
  font: 700 13px/1.2 var(--font-ui);
  text-decoration: none;
  transition: opacity 180ms ease;
}

:slotted(.auth-footer__link:hover) {
  opacity: 0.75;
}

:global(.auth-footer__icon) {
  font-size: 18px;
}

@media (max-width: 720px) {
  .auth-card {
    padding: 24px 18px;
  }

  .auth-logo {
    width: 64px;
    height: 64px;
  }
}
</style>
