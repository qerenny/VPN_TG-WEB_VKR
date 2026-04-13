<script setup lang="ts">
import { computed, ref } from 'vue'

const model = defineModel<string>({ required: true })

const props = withDefaults(defineProps<{
  label: string
  autocomplete: string
  required?: boolean
}>(), {
  required: true,
})

const isVisible = ref(false)

const inputType = computed(() => isVisible.value ? 'text' : 'password')
const toggleLabel = computed(() => isVisible.value ? 'Скрыть пароль' : 'Показать пароль')
const toggleIcon = computed(() => isVisible.value ? 'visibility_off' : 'visibility')
</script>

<template>
  <label class="auth-field auth-password-field">
    <span class="cabinet-form-label">{{ props.label }}</span>
    <span class="auth-password-field__control">
      <input
        v-model="model"
        class="cabinet-input auth-password-field__input"
        :type="inputType"
        :autocomplete="props.autocomplete"
        :required="props.required"
      />
      <button
        class="auth-password-field__toggle"
        type="button"
        :aria-label="toggleLabel"
        :title="toggleLabel"
        @click="isVisible = !isVisible"
      >
        <span class="material-symbols-outlined" aria-hidden="true">{{ toggleIcon }}</span>
      </button>
    </span>
  </label>
</template>

<style scoped>
.auth-password-field {
  display: grid;
  gap: 6px;
}

.auth-password-field__control {
  position: relative;
  display: block;
}

.auth-password-field__input {
  padding-right: 48px;
}

.auth-password-field__toggle {
  position: absolute;
  top: 50%;
  right: 8px;
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(30, 51, 82, 0.68);
  cursor: pointer;
  transition: background-color 180ms ease, color 180ms ease;
  transform: translateY(-50%);
}

.auth-password-field__toggle:hover,
.auth-password-field__toggle:focus-visible {
  background: rgba(77, 143, 214, 0.1);
  color: #1e3352;
}

.auth-password-field__toggle:focus-visible {
  outline: 2px solid rgba(77, 143, 214, 0.35);
  outline-offset: 2px;
}

.auth-password-field__toggle .material-symbols-outlined {
  font-size: 20px;
}
</style>
