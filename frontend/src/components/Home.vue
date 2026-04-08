<template>
  <main class="page-shell">
    <section class="hero glass-card">
      <div class="hero__halo" aria-hidden="true"></div>
      <div class="hero__spark hero__spark--one"></div>
      <div class="hero__spark hero__spark--two"></div>
      <div class="hero__particles" aria-hidden="true">
        <span class="hero__particle hero__particle--1"></span>
        <span class="hero__particle hero__particle--2"></span>
        <span class="hero__particle hero__particle--3"></span>
        <span class="hero__particle hero__particle--4"></span>
        <span class="hero__particle hero__particle--5"></span>
      </div>
      <div class="hero__badge hero__badge--one" aria-hidden="true">быстрый старт</div>
      <div class="hero__badge hero__badge--two" aria-hidden="true">защищённый доступ</div>
      <div class="hero__badge hero__badge--three" aria-hidden="true">бот и веб-панель</div>

      <div class="hero__brand">
        <img src="/favicon.svg" alt="Логотип сервиса" class="hero__logo" />
        <p class="hero__chip">Защищённый удалённый доступ</p>
      </div>

      <h1 class="brand-title hero__title">Remote Access</h1>
      <p class="hero__lead">
        Управляйте доступом через чат-бота или веб-панель.
        Получайте конфигурации, проверяйте срок действия и подключайте устройства.
      </p>

      <div class="hero__actions">
        <RouterLink to="/auth/login" class="hero__cta">
          <span class="material-symbols-outlined" aria-hidden="true">login</span>
          Войти в кабинет
        </RouterLink>
        <RouterLink to="/app/subscriptions" class="hero__cta hero__cta--ghost">
          <span class="material-symbols-outlined" aria-hidden="true">vpn_key</span>
          Мои конфигурации
        </RouterLink>
      </div>

      <p class="hero__hint">Чат-бот остаётся основным интерфейсом, веб-панель доступна как дополнительный сценарий.</p>
    </section>
  </main>
</template>

<script setup>
</script>

<style scoped>
.hero {
  position: relative;
  overflow: hidden;
  margin: min(12vh, 100px) auto 0;
  width: min(760px, 100%);
  padding: clamp(24px, 5vw, 48px);
  text-align: center;
  animation: card-rise 700ms cubic-bezier(0.19, 1, 0.22, 1);
}

.hero__halo {
  position: absolute;
  inset: 16% 24% auto;
  height: 220px;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(255, 156, 95, 0.2), rgba(255, 156, 95, 0));
  filter: blur(10px);
  z-index: -1;
  animation: halo-breathe 7s ease-in-out infinite;
}

.hero__spark {
  position: absolute;
  z-index: -1;
  border-radius: 999px;
  filter: blur(2px);
  animation: orbit 9s ease-in-out infinite;
}

.hero__spark--one {
  width: min(34vw, 220px);
  height: min(34vw, 220px);
  top: -80px;
  right: -70px;
  background: radial-gradient(circle, rgba(255, 116, 87, 0.32), transparent 70%);
}

.hero__spark--two {
  width: min(32vw, 190px);
  height: min(32vw, 190px);
  bottom: -80px;
  left: -60px;
  background: radial-gradient(circle, rgba(255, 163, 75, 0.3), transparent 70%);
  animation-delay: -4.5s;
}

.hero__particles {
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
}

.hero__particle {
  position: absolute;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(255, 173, 95, 0.4));
  box-shadow: 0 0 0 7px rgba(255, 255, 255, 0.08);
  opacity: 0.72;
  animation: particle-drift 11s linear infinite;
}

.hero__particle--1 {
  top: 18%;
  left: 16%;
}

.hero__particle--2 {
  top: 28%;
  right: 18%;
  width: 8px;
  height: 8px;
  animation-delay: -2.2s;
}

.hero__particle--3 {
  bottom: 22%;
  left: 20%;
  width: 10px;
  height: 10px;
  animation-delay: -5.4s;
}

.hero__particle--4 {
  right: 24%;
  bottom: 18%;
  width: 14px;
  height: 14px;
  animation-delay: -7.1s;
}

.hero__particle--5 {
  top: 14%;
  left: 50%;
  width: 6px;
  height: 6px;
  animation-delay: -3.8s;
}

.hero__badge {
  position: absolute;
  z-index: 1;
  padding: 9px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(255, 129, 91, 0.24);
  box-shadow: 0 14px 22px rgba(194, 92, 52, 0.12);
  color: #9a4b3a;
  font-family: 'Lato', sans-serif;
  font-size: 13px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  backdrop-filter: blur(10px);
  animation: badge-float 8.5s ease-in-out infinite;
}

.hero__badge--one {
  top: 24px;
  left: 24px;
}

.hero__badge--two {
  top: 92px;
  right: 28px;
  animation-delay: -2.8s;
}

.hero__badge--three {
  right: 56px;
  bottom: 30px;
  animation-delay: -5.1s;
}

.hero__brand {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  gap: 12px;
}

.hero__logo {
  width: clamp(86px, 18vw, 124px);
  height: clamp(86px, 18vw, 124px);
  border-radius: 50%;
  border: 4px solid rgba(255, 90, 68, 0.35);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 12px 34px rgba(151, 53, 34, 0.22);
  animation: logo-bob 6s ease-in-out infinite;
}

.hero__chip {
  margin: 0;
  font-size: clamp(13px, 2.4vw, 15px);
  color: var(--muted);
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(255, 122, 81, 0.26);
  border-radius: 999px;
  padding: 7px 14px;
}

.hero__title {
  margin: 14px 0 8px;
  font-size: clamp(44px, 8vw, 78px);
  line-height: 1;
  color: #de4c38;
}

.hero__lead {
  margin: 0 auto;
  max-width: 530px;
  font-family: 'Lato', sans-serif;
  font-size: clamp(17px, 3.3vw, 22px);
  line-height: 1.55;
  color: #513636;
}

.hero__actions {
  display: grid;
  gap: 12px;
  margin-top: clamp(22px, 4vw, 32px);
}

.hero__cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-width: min(350px, 100%);
  padding: 14px 26px;
  border-radius: 16px;
  border: 1px solid rgba(255, 92, 66, 0.44);
  background: linear-gradient(120deg, var(--accent), var(--accent-2));
  color: white;
  text-decoration: none;
  font-size: clamp(18px, 3.2vw, 22px);
  font-family: 'Lato', sans-serif;
  font-weight: 700;
  letter-spacing: 0.01em;
  box-shadow: 0 14px 24px rgba(197, 70, 42, 0.34);
  transition: transform 240ms ease, box-shadow 240ms ease, filter 240ms ease;
  position: relative;
  overflow: hidden;
}

.hero__cta--ghost {
  background: rgba(255, 255, 255, 0.7);
  color: #9a4b3a;
  border-color: rgba(255, 122, 81, 0.26);
  box-shadow: 0 10px 18px rgba(194, 92, 52, 0.1);
}

.hero__cta::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 28%, rgba(255, 255, 255, 0.3) 50%, transparent 72%);
  transform: translateX(-140%);
  animation: cta-sheen 4.8s ease-in-out infinite;
}

.hero__cta--ghost::after {
  display: none;
}

.hero__cta:hover {
  transform: translateY(-3px) scale(1.02);
  box-shadow: 0 18px 28px rgba(197, 70, 42, 0.4);
  filter: saturate(1.08);
}

.hero__cta--ghost:hover {
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 14px 22px rgba(194, 92, 52, 0.14);
}

.hero__hint {
  margin: 12px 0 2px;
  font-size: 14px;
  color: #7b5b58;
}

@keyframes card-rise {
  from {
    opacity: 0;
    transform: translateY(24px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes orbit {
  0%, 100% {
    transform: translate(0, 0);
  }
  50% {
    transform: translate(-14px, 12px);
  }
}

@keyframes halo-breathe {
  0%, 100% {
    opacity: 0.5;
    transform: scale(0.94);
  }
  50% {
    opacity: 0.9;
    transform: scale(1.08);
  }
}

@keyframes particle-drift {
  0% {
    transform: translate3d(0, 0, 0) scale(0.9);
    opacity: 0;
  }
  18% {
    opacity: 0.72;
  }
  50% {
    transform: translate3d(14px, -18px, 0) scale(1.08);
    opacity: 0.9;
  }
  100% {
    transform: translate3d(-10px, -34px, 0) scale(0.88);
    opacity: 0;
  }
}

@keyframes badge-float {
  0%, 100% {
    transform: translate3d(0, 0, 0) rotate(0deg);
  }
  50% {
    transform: translate3d(0, -10px, 0) rotate(-1.5deg);
  }
}

@keyframes logo-bob {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-8px);
  }
}

@keyframes cta-sheen {
  0%, 60%, 100% {
    transform: translateX(-140%);
  }
  78% {
    transform: translateX(140%);
  }
}

@media (max-width: 680px) {
  .hero {
    margin-top: min(8vh, 70px);
    padding-top: 92px;
  }

  .hero__cta {
    width: 100%;
  }

  .hero__badge {
    font-size: 11px;
    padding: 8px 12px;
  }

  .hero__badge--one {
    top: 18px;
    left: 18px;
  }

  .hero__badge--two {
    top: 56px;
    right: 18px;
  }

  .hero__badge--three {
    right: 18px;
    bottom: 18px;
  }
}
</style>
