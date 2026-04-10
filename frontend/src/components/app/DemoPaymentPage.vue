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
  <div class="cabinet-shell page-shell demo-payment-shell">
    <section class="cabinet-section demo-payment-section">
      <div class="cabinet-section__head">
        <p class="cabinet-kicker">Демонстрационный платёж</p>
        <h1 class="cabinet-title">Внешний платёжный шлюз</h1>
        <p class="cabinet-copy">
          В дипломной сборке реальная эквайринговая интеграция заменена демонстрационным контуром.
          Сервис создаёт платёжную заявку и имитирует подтверждение через фонового обработчика.
        </p>
      </div>

      <article class="glass-card cabinet-panel demo-payment__panel">
        <div class="cabinet-facts">
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">Провайдер</p>
            <p class="cabinet-fact__value">{{ provider }}</p>
          </div>
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">Конфигурация</p>
            <p class="cabinet-fact__value">{{ product }}</p>
          </div>
          <div class="cabinet-fact demo-payment__fact--wide">
            <p class="cabinet-fact__label">Платёж</p>
            <p class="cabinet-fact__value demo-payment__fact-id">{{ paymentId }}</p>
          </div>
          <div v-if="amountRub" class="cabinet-fact">
            <p class="cabinet-fact__label">Сумма</p>
            <p class="cabinet-fact__value">{{ amountRub }}</p>
          </div>
        </div>

        <div class="cabinet-actions demo-payment__actions">
          <a class="cabinet-btn cabinet-btn--primary" :href="returnUrl">
            <span class="material-symbols-outlined">arrow_back</span>
            Вернуться к статусу платежа
          </a>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.demo-payment-shell {
  display: flex;
  align-items: center;
  justify-content: center;
}

.demo-payment-section {
  width: min(720px, 100%);
  margin: 0 auto;
}

.demo-payment__panel {
  display: grid;
  gap: 24px;
}

.demo-payment__fact--wide {
  grid-column: 1 / -1;
}

.demo-payment__fact-id {
  word-break: break-all;
  font-size: 14px;
}

.demo-payment__actions {
  justify-content: flex-end;
}

@media (max-width: 560px) {
  .demo-payment__actions {
    justify-content: stretch;
  }

  .demo-payment__actions .cabinet-btn {
    width: 100%;
  }
}
</style>
