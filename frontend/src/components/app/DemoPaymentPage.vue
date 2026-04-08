<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const provider = computed(() => String(route.query.provider || 'Платёжный шлюз'))
const product = computed(() => String(route.query.product || 'Доступ'))
const paymentId = computed(() => String(route.query.payment_id || 'demo-payment'))
const returnUrl = computed(() => String(route.query.return_url || '/app/payments'))
const amountRub = computed(() => {
  const amount = Number(route.query.amount || 0)
  if (!Number.isFinite(amount) || amount <= 0) {
    return ''
  }
  return `${(amount / 100).toLocaleString('ru-RU')} RUB`
})
</script>

<template>
  <main class="demo-payment">
    <section class="glass-card demo-payment__panel">
      <p class="cabinet-kicker">Демонстрационный платёж</p>
      <h1 class="cabinet-title">Внешний платёжный шлюз</h1>
      <p class="cabinet-copy">
        В дипломной сборке реальная эквайринговая интеграция заменена демонстрационным контуром.
        Сервис создаёт платёжную заявку и имитирует подтверждение через фонового обработчика.
      </p>

      <div class="demo-payment__facts">
        <div class="cabinet-fact">
          <p class="cabinet-fact__label">Провайдер</p>
          <p class="cabinet-fact__value">{{ provider }}</p>
        </div>
        <div class="cabinet-fact">
          <p class="cabinet-fact__label">Конфигурация</p>
          <p class="cabinet-fact__value">{{ product }}</p>
        </div>
        <div class="cabinet-fact">
          <p class="cabinet-fact__label">Платёж</p>
          <p class="cabinet-fact__value">{{ paymentId }}</p>
        </div>
        <div v-if="amountRub" class="cabinet-fact">
          <p class="cabinet-fact__label">Сумма</p>
          <p class="cabinet-fact__value">{{ amountRub }}</p>
        </div>
      </div>

      <div class="cabinet-actions">
        <a class="cabinet-btn cabinet-btn--primary" :href="returnUrl">
          Вернуться к статусу платежа
        </a>
      </div>
    </section>
  </main>
</template>

<style scoped>
.demo-payment {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 16px;
  background:
    radial-gradient(circle at 20% 10%, rgba(77, 143, 214, 0.12), transparent 32%),
    linear-gradient(145deg, #f5f8fb, #ffffff);
}

.demo-payment__panel {
  width: min(720px, 100%);
  display: grid;
  gap: 20px;
}

.demo-payment__facts {
  display: grid;
  gap: 12px;
}
</style>
