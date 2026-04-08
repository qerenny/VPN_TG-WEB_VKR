<template>
  <main class="page-shell error-page">
    <div class="auth-scene" aria-hidden="true">
      <div class="auth-scene__orb auth-scene__orb--one"></div>
      <div class="auth-scene__orb auth-scene__orb--two"></div>
      <div class="auth-scene__ring auth-scene__ring--one"></div>
      <span class="auth-scene__dot auth-scene__dot--one"></span>
      <span class="auth-scene__dot auth-scene__dot--two"></span>
    </div>

    <section class="error glass-card cabinet-panel">
      <img src="/favicon.svg" alt="Логотип сервиса" class="error__logo" />

      <p class="error__code">404</p>
      <h1 class="brand-title error__title">Страница не найдена</h1>
      <p class="error__text">
        Проверьте ссылку или запросите новую у поддержки.
      </p>
      <div class="error__actions">
        <a href="/" class="cabinet-btn cabinet-btn--warm">
          <span class="material-symbols-outlined">home</span>
          На главную
        </a>
        <RouterLink to="/auth/login" class="cabinet-btn cabinet-btn--ghost">
          <span class="material-symbols-outlined">login</span>
          Войти в кабинет
        </RouterLink>
      </div>
    </section>
  </main>
</template>

<script setup>
</script>

<style scoped>
.error-page {
  display: grid;
  place-items: center;
}

.error {
  width: min(560px, 100%);
  text-align: center;
}

.error__logo {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  border: 3px solid rgba(255, 90, 68, 0.3);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 24px rgba(151, 53, 34, 0.18);
  margin: 0 auto 8px;
  animation: float-soft 4s ease-in-out infinite;
}

.error__code {
  margin: 0;
  font: 700 clamp(56px, 14vw, 110px)/0.9 var(--font-ui);
  color: rgba(255, 79, 56, 0.75);
}

.error__title {
  margin: 4px 0 12px;
  color: var(--accent);
  font-size: clamp(30px, 7vw, 52px);
  line-height: 1;
}

.error__text {
  margin: 0 auto;
  max-width: 380px;
  font-size: clamp(16px, 3vw, 20px);
  line-height: 1.5;
  color: var(--muted);
}

.error__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
  margin-top: 24px;
}
</style>
