<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'

type TelegramWebApp = {
  ready?: () => void
  expand?: () => void
  disableVerticalSwipes?: () => void
  setHeaderColor?: (color: string) => void
  setBackgroundColor?: (color: string) => void
  themeParams?: {
    bg_color?: string
    secondary_bg_color?: string
    text_color?: string
    hint_color?: string
    button_color?: string
  }
}

onMounted(() => {
  const telegram = (window as typeof window & {
    Telegram?: { WebApp?: TelegramWebApp }
  }).Telegram?.WebApp

  if (!telegram) {
    return
  }

  document.documentElement.dataset.telegramMiniApp = 'true'

  try {
    telegram.ready?.()
    telegram.expand?.()
    telegram.disableVerticalSwipes?.()
    telegram.setHeaderColor?.('#fef7f1')
    telegram.setBackgroundColor?.('#fef7f1')
  } catch {
    // Telegram WebApp bridge is best-effort for local/dev and older clients.
  }

  const theme = telegram.themeParams || {}
  if (theme.bg_color) {
    document.documentElement.style.setProperty('--tg-bg-color', theme.bg_color)
  }
  if (theme.secondary_bg_color) {
    document.documentElement.style.setProperty('--tg-secondary-bg-color', theme.secondary_bg_color)
  }
  if (theme.text_color) {
    document.documentElement.style.setProperty('--tg-text-color', theme.text_color)
  }
  if (theme.hint_color) {
    document.documentElement.style.setProperty('--tg-hint-color', theme.hint_color)
  }
  if (theme.button_color) {
    document.documentElement.style.setProperty('--tg-button-color', theme.button_color)
  }
})
</script>

<style>
@font-face {
  font-family: 'Lato';
  src: url('/fonts/lato-regular.woff2') format('woff2');
  font-style: normal;
  font-weight: 400;
  font-display: swap;
}

@font-face {
  font-family: 'Open Sans';
  src: url('/fonts/open-sans-regular.woff2') format('woff2');
  font-style: normal;
  font-weight: 400;
  font-display: swap;
}

@font-face {
  font-family: 'Material Symbols Outlined';
  src: url('/fonts/material-symbols-outlined.woff2') format('woff2');
  font-style: normal;
  font-weight: 400;
  font-display: block;
}

:root {
  --font-ui: 'Lato', sans-serif;
  --font-text: 'Open Sans', sans-serif;
  --font-brand: 'Lato', sans-serif;
  --tg-bg-color: #fef7f1;
  --tg-secondary-bg-color: #fff8f3;
  --tg-text-color: #2a1512;
  --tg-hint-color: #6b4846;
  --tg-button-color: #ff4f38;

  /* ── richer warm palette ── */
  --bg-0: #fef6f0;
  --bg-1: #fdd9c4;
  --bg-2: #f9b89e;
  --ink: #2a1512;
  --muted: #6b4846;
  --accent: #ff4f38;
  --accent-2: #ff8726;
  --accent-glow: rgba(255, 79, 56, 0.35);
  --card: rgba(255, 255, 255, 0.78);
  --stroke: rgba(255, 120, 85, 0.22);
  --shadow: 0 20px 60px rgba(140, 48, 30, 0.16), 0 4px 16px rgba(140, 48, 30, 0.08);
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  min-height: 100vh;
  background:
    radial-gradient(ellipse 80% 60% at 10% 5%, rgba(255, 100, 70, 0.28), transparent),
    radial-gradient(ellipse 70% 50% at 90% 10%, rgba(255, 160, 80, 0.32), transparent),
    radial-gradient(ellipse 60% 50% at 75% 85%, rgba(255, 90, 130, 0.2), transparent),
    radial-gradient(ellipse 50% 40% at 20% 80%, rgba(255, 180, 120, 0.18), transparent),
    linear-gradient(155deg, var(--bg-0), var(--bg-1) 50%, var(--bg-2));
  color: var(--ink);
  font-family: var(--font-text);
}

html[data-telegram-mini-app='true'] body {
  background:
    radial-gradient(ellipse 80% 60% at 10% 5%, rgba(255, 100, 70, 0.22), transparent),
    radial-gradient(ellipse 70% 50% at 90% 10%, rgba(255, 160, 80, 0.24), transparent),
    linear-gradient(155deg, var(--tg-bg-color), var(--tg-secondary-bg-color));
  color: var(--tg-text-color);
}

a {
  color: inherit;
}

button,
input,
textarea,
select {
  font: inherit;
}

/* ── Page shell ── */
.page-shell {
  position: relative;
  isolation: isolate;
  min-height: 100vh;
  min-height: 100dvh;
  padding: 28px 18px 48px;
}

.page-shell::before,
.page-shell::after {
  content: '';
  position: fixed;
  border-radius: 999px;
  filter: blur(8px);
  z-index: -1;
  pointer-events: none;
  animation: float-ambient 14s ease-in-out infinite;
}

.page-shell::before {
  width: min(46vw, 420px);
  height: min(46vw, 420px);
  top: -130px;
  left: -100px;
  background: radial-gradient(circle, rgba(255, 80, 56, 0.3), transparent 64%);
}

.page-shell::after {
  width: min(42vw, 380px);
  height: min(42vw, 380px);
  right: -110px;
  bottom: -140px;
  background: radial-gradient(circle, rgba(255, 135, 60, 0.28), transparent 62%);
  animation-delay: -7s;
}

/* ── Glass card ── */
.glass-card {
  background: var(--card);
  border: 1px solid var(--stroke);
  border-radius: 28px;
  backdrop-filter: blur(14px);
  box-shadow: var(--shadow);
}

/* ── Auth scene decorations ── */
.auth-scene {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: -1;
  overflow: hidden;
}

.auth-scene__orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(12px);
}

.auth-scene__orb--one {
  top: 30px;
  right: min(6vw, 60px);
  width: min(28vw, 260px);
  height: min(28vw, 260px);
  background: radial-gradient(circle, rgba(255, 100, 70, 0.25), transparent 64%);
  animation: float-ambient 14s ease-in-out infinite;
}

.auth-scene__orb--two {
  left: min(4vw, 40px);
  bottom: 10%;
  width: min(24vw, 220px);
  height: min(24vw, 220px);
  background: radial-gradient(circle, rgba(255, 145, 60, 0.22), transparent 62%);
  animation: float-ambient 12s ease-in-out infinite reverse;
}

.auth-scene__ring {
  position: absolute;
  border-radius: 50%;
  border: 1.5px solid rgba(255, 120, 85, 0.16);
}

.auth-scene__ring--one {
  top: 50px;
  left: 6%;
  width: min(30vw, 280px);
  height: min(30vw, 280px);
  animation: slow-spin 40s linear infinite;
}

.auth-scene__dot {
  position: absolute;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(255, 135, 60, 0.5));
  box-shadow: 0 0 0 6px rgba(255, 255, 255, 0.1);
}

.auth-scene__dot--one {
  top: 22%;
  left: 14%;
  width: 10px;
  height: 10px;
  animation: float-ambient 10s ease-in-out infinite;
}

.auth-scene__dot--two {
  bottom: 16%;
  right: 16%;
  width: 7px;
  height: 7px;
  animation: float-ambient 10s ease-in-out infinite;
  animation-delay: -5s;
}

/* ── Paw prints decoration (CSS-only) ── */
.paw-prints {
  position: absolute;
  pointer-events: none;
  z-index: -1;
  overflow: hidden;
  inset: 0;
}

.paw-print {
  position: absolute;
  width: 24px;
  height: 24px;
  opacity: 0.06;
  font-size: 24px;
  font-family: 'Material Symbols Outlined';
  color: var(--accent);
}

.paw-print--1 { top: 12%; left: 8%; transform: rotate(-25deg); }
.paw-print--2 { top: 35%; right: 6%; transform: rotate(15deg); }
.paw-print--3 { bottom: 20%; left: 15%; transform: rotate(-10deg); }
.paw-print--4 { bottom: 40%; right: 12%; transform: rotate(30deg); }
.paw-print--5 { top: 60%; left: 5%; transform: rotate(-35deg); }

/* ── Cabinet shell ── */
.cabinet-shell {
  --cabinet-surface: rgba(255, 255, 255, 0.82);
  --cabinet-surface-strong: rgba(252, 248, 244, 0.94);
  --cabinet-stroke: rgba(255, 120, 85, 0.16);
  --cabinet-text: #1e3352;
  --cabinet-muted: #5a6e87;
  --cabinet-soft: #7b91ab;
  --cabinet-standard: #f5a04e;
  --cabinet-standard-2: #f07e4a;
  --cabinet-traffic_limited: #4d8fd6;
  --cabinet-traffic_limited-2: #3ebfb0;
  --cabinet-ok: #3da866;
  --cabinet-danger: #d65858;
  width: min(1260px, 100%);
  margin: 0 auto;
  color: var(--cabinet-text);
}

.cabinet-shell.page-shell {
  padding: 24px 20px 56px;
  background:
    radial-gradient(ellipse 50% 40% at 8% 12%, rgba(255, 100, 70, 0.2), transparent),
    radial-gradient(ellipse 40% 35% at 88% 8%, rgba(77, 143, 214, 0.14), transparent),
    radial-gradient(ellipse 45% 40% at 80% 85%, rgba(255, 160, 80, 0.14), transparent),
    radial-gradient(ellipse 35% 30% at 15% 90%, rgba(62, 191, 176, 0.1), transparent),
    linear-gradient(168deg, #fef7f1 0%, #f8ede5 50%, #f2e4da 100%);
}

.cabinet-shell.page-shell::before {
  background: radial-gradient(circle, rgba(77, 143, 214, 0.24), transparent 64%);
  top: -110px;
  left: -80px;
}

.cabinet-shell.page-shell::after {
  background: radial-gradient(circle, rgba(62, 191, 176, 0.18), transparent 62%);
  right: -90px;
  bottom: -120px;
}

.cabinet-shell .glass-card {
  background: var(--cabinet-surface);
  border: 1px solid rgba(255, 120, 85, 0.14);
  border-radius: 24px;
  box-shadow:
    0 20px 50px rgba(140, 52, 30, 0.1),
    0 2px 8px rgba(140, 52, 30, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(14px);
}

/* ── Cabinet panel ── */
.cabinet-panel {
  position: relative;
  overflow: hidden;
  padding: clamp(22px, 3vw, 30px);
  animation: cabinet-rise 420ms cubic-bezier(0.19, 1, 0.22, 1) both;
}

.cabinet-panel::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 88% 14%, rgba(255, 255, 255, 0.5), transparent 24%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0));
  pointer-events: none;
}

/* ── Grid ── */
.cabinet-grid {
  display: grid;
  gap: 20px;
}

.cabinet-grid--2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.cabinet-grid--3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

/* ── Section ── */
.cabinet-section {
  display: grid;
  gap: 20px;
  margin-top: 20px;
}

.cabinet-section__head {
  display: grid;
  gap: 8px;
}

/* ── Typography ── */
.cabinet-kicker {
  margin: 0;
  color: var(--cabinet-traffic_limited);
  font: 700 12px/1.2 var(--font-ui);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.cabinet-title {
  margin: 0;
  font: 700 clamp(26px, 4vw, 36px)/1.1 var(--font-ui);
  color: var(--cabinet-text);
}

.cabinet-copy {
  margin: 0;
  max-width: 70ch;
  color: var(--cabinet-muted);
  line-height: 1.65;
}

.cabinet-subtitle {
  margin: 0;
  font: 700 21px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

/* ── Badges ── */
.cabinet-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: fit-content;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(77, 143, 214, 0.12);
  border: 1px solid rgba(77, 143, 214, 0.2);
  color: #1d5a94;
  font: 700 11px/1 var(--font-ui);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.cabinet-badge--warm {
  background: rgba(245, 160, 78, 0.14);
  border-color: rgba(240, 126, 74, 0.22);
  color: #964520;
}

.cabinet-badge--ok {
  background: rgba(61, 168, 102, 0.12);
  border-color: rgba(61, 168, 102, 0.2);
  color: #267a48;
}

.cabinet-badge--off {
  background: rgba(214, 88, 88, 0.1);
  border-color: rgba(214, 88, 88, 0.16);
  color: #a13c3c;
}

.cabinet-badge--danger {
  background: rgba(214, 88, 88, 0.1);
  border-color: rgba(214, 88, 88, 0.18);
  color: #a13c3c;
}

.cabinet-badge--muted {
  background: rgba(90, 110, 135, 0.08);
  border-color: rgba(90, 110, 135, 0.14);
  color: var(--cabinet-muted);
}

/* ── Stack ── */
.cabinet-stack {
  display: grid;
  gap: 16px;
}

/* ── Metrics ── */
.cabinet-metrics {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}

.cabinet-metric {
  min-width: 0;
  padding: 16px 18px;
  border-radius: 18px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.7), rgba(255, 250, 246, 0.5));
  border: 1px solid rgba(126, 170, 220, 0.12);
  transition: transform 200ms ease, box-shadow 200ms ease;
}

.cabinet-metric:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(100, 120, 150, 0.08);
}

.cabinet-metric__label {
  margin: 0;
  color: var(--cabinet-soft);
  font: 700 10px/1.2 var(--font-ui);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.cabinet-metric__value {
  margin: 8px 0 0;
  font: 700 clamp(18px, 2.6vw, 24px)/1.2 var(--font-ui);
  color: var(--cabinet-text);
  word-break: break-word;
}

/* ── Facts ── */
.cabinet-facts {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}

.cabinet-fact {
  padding: 16px 18px;
  border-radius: 18px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.7), rgba(255, 250, 246, 0.5));
  border: 1px solid rgba(126, 170, 220, 0.12);
}

.cabinet-fact__label {
  margin: 0;
  color: var(--cabinet-soft);
  font: 700 10px/1.2 var(--font-ui);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.cabinet-fact__value {
  margin: 8px 0 0;
  color: var(--cabinet-text);
  font: 700 15px/1.45 var(--font-text);
}

/* ── Actions ── */
.cabinet-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

/* ── Buttons ── */
.cabinet-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 48px;
  padding: 0 20px;
  border-radius: 16px;
  border: 1px solid rgba(255, 130, 85, 0.14);
  background: rgba(255, 255, 255, 0.84);
  color: var(--cabinet-text, var(--ink));
  text-decoration: none;
  font: 700 14px/1.2 var(--font-ui);
  cursor: pointer;
  transition: transform 200ms ease, border-color 200ms ease, background-color 200ms ease, box-shadow 200ms ease;
}

.cabinet-btn:hover {
  transform: translateY(-2px);
  border-color: rgba(126, 170, 220, 0.22);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 8px 20px rgba(100, 80, 60, 0.08);
}

.cabinet-btn:active {
  transform: translateY(0);
}

.cabinet-btn:disabled {
  opacity: 0.6;
  cursor: wait;
  transform: none;
}

.cabinet-btn--primary {
  overflow: hidden;
  border-color: rgba(77, 143, 214, 0.3);
  background: linear-gradient(135deg, #3b82d4, #4db8b0);
  box-shadow: 0 12px 32px rgba(59, 130, 212, 0.3);
  color: #fff;
}

.cabinet-btn--primary:hover {
  box-shadow: 0 16px 36px rgba(59, 130, 212, 0.36);
  background: linear-gradient(135deg, #4590e0, #56c4bb);
}

.cabinet-btn--primary::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 20%, rgba(255, 255, 255, 0.28) 50%, transparent 80%);
  transform: translateX(-140%);
  animation: cta-sheen 5s ease-in-out infinite;
}

.cabinet-btn--warm {
  overflow: hidden;
  border-color: rgba(240, 126, 74, 0.28);
  background: linear-gradient(135deg, #f07e4a, #f5a04e);
  box-shadow: 0 12px 32px rgba(240, 126, 74, 0.3);
  color: #fff;
}

.cabinet-btn--warm:hover {
  box-shadow: 0 16px 36px rgba(240, 126, 74, 0.36);
  background: linear-gradient(135deg, #f58b5a, #f7ad60);
}

.cabinet-btn--warm::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 20%, rgba(255, 255, 255, 0.28) 50%, transparent 80%);
  transform: translateX(-140%);
  animation: cta-sheen 5s ease-in-out infinite;
}

.cabinet-btn--ghost {
  background: rgba(255, 248, 243, 0.9);
  border-color: rgba(255, 130, 85, 0.12);
  color: #9a4020;
}

.cabinet-btn--ghost:hover {
  background: rgba(255, 243, 236, 1);
}

/* ── Inputs ── */
.cabinet-input,
.cabinet-checkbox {
  font: 400 15px/1.45 var(--font-text);
}

.cabinet-input {
  width: 100%;
  border: 1.5px solid rgba(100, 150, 210, 0.16);
  border-radius: 14px;
  padding: 13px 16px;
  background: rgba(255, 255, 255, 0.92);
  color: #1e3352;
  outline: none;
  transition: border-color 180ms ease, box-shadow 180ms ease, background-color 180ms ease;
}

.cabinet-input:hover:not(:focus) {
  border-color: rgba(100, 150, 210, 0.28);
}

.cabinet-input:focus {
  border-color: rgba(77, 143, 214, 0.4);
  box-shadow: 0 0 0 3px rgba(77, 143, 214, 0.12);
  background: #fff;
}

.cabinet-inline-form {
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.cabinet-note {
  margin: 0;
  color: var(--cabinet-muted);
  line-height: 1.6;
}

.cabinet-alert {
  display: grid;
  gap: 14px;
  background:
    radial-gradient(circle at top right, rgba(77, 143, 214, 0.1), transparent 32%),
    rgba(255, 250, 246, 0.94);
}

.cabinet-empty {
  display: grid;
  place-items: center;
  gap: 14px;
  min-height: 200px;
  text-align: center;
  color: var(--cabinet-muted);
}

/* Spinning logo loader */
.cabinet-loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 32px 16px;
  min-height: 180px;
}

.cabinet-loader__img {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 2.5px solid rgba(255, 90, 68, 0.25);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 6px 18px rgba(151, 53, 34, 0.12);
  animation: loader-spin 1.8s cubic-bezier(0.6, 0.15, 0.35, 0.85) infinite;
}

.cabinet-loader__text {
  margin: 0;
  font: 400 14px/1.4 var(--font-text);
  color: var(--cabinet-muted, var(--muted));
}

@keyframes loader-spin {
  0% { transform: rotate(0deg) scale(1); }
  50% { transform: rotate(180deg) scale(0.92); }
  100% { transform: rotate(360deg) scale(1); }
}

.cabinet-table {
  display: grid;
  gap: 10px;
}

.cabinet-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.65), rgba(255, 250, 246, 0.45));
  border: 1px solid rgba(126, 170, 220, 0.1);
  transition: transform 180ms ease, box-shadow 180ms ease;
}

.cabinet-row:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(90, 110, 140, 0.08);
}

/* ── Form label ── */
.cabinet-form-label {
  margin: 0;
  color: var(--cabinet-soft, var(--muted));
  font: 700 11px/1.2 var(--font-ui);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

/* ── Toggle switch ── */
.cabinet-toggle {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}

.cabinet-toggle input {
  opacity: 0;
  width: 0;
  height: 0;
  position: absolute;
}

.cabinet-toggle__track {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: rgba(126, 170, 220, 0.2);
  border: 1px solid rgba(126, 170, 220, 0.14);
  transition: background-color 220ms ease, border-color 220ms ease;
  cursor: pointer;
}

.cabinet-toggle__track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
  transition: transform 220ms ease;
}

.cabinet-toggle input:checked + .cabinet-toggle__track {
  background: linear-gradient(135deg, #3b82d4, #4db8b0);
  border-color: rgba(77, 143, 214, 0.3);
}

.cabinet-toggle input:checked + .cabinet-toggle__track::after {
  transform: translateX(20px);
}

.cabinet-toggle input:focus-visible + .cabinet-toggle__track {
  box-shadow: 0 0 0 3px rgba(77, 143, 214, 0.2);
}

/* ── Visual mark utility ── */
.visual-mark {
  display: block;
  max-width: 100%;
  height: auto;
}

.visual-mark--float {
  animation: float-soft 4s ease-in-out infinite;
}

.visual-mark--sm { width: 64px; }
.visual-mark--md { width: 96px; }
.visual-mark--lg { width: 140px; }

/* ── Keyframes ── */
@keyframes cabinet-rise {
  from {
    opacity: 0;
    transform: translateY(12px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes cta-sheen {
  0%, 70%, 100% {
    transform: translateX(-140%);
  }
  82% {
    transform: translateX(140%);
  }
}

@keyframes float-ambient {
  0%, 100% {
    transform: translateY(0) translateX(0);
  }
  50% {
    transform: translateY(-18px) translateX(12px);
  }
}

@keyframes float-soft {
  0%, 100% {
    transform: translateY(0) rotate(0deg);
  }
  25% {
    transform: translateY(-6px) rotate(-1deg);
  }
  75% {
    transform: translateY(-3px) rotate(1deg);
  }
}

@keyframes slow-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes pulse-soft {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.04); }
}

@keyframes blink {
  0%, 42%, 44%, 100% { transform: scaleY(1); }
  43% { transform: scaleY(0.1); }
}

/* ── Responsive ── */
@media (max-width: 980px) {
  .cabinet-grid--2,
  .cabinet-grid--3 {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 720px) {
  .page-shell {
    padding: 20px 14px 40px;
  }

  .cabinet-shell.page-shell {
    padding: 20px 14px 48px;
  }

  .cabinet-inline-form {
    grid-template-columns: minmax(0, 1fr);
  }

  .cabinet-row {
    flex-direction: column;
    align-items: flex-start;
  }
}

/* ── Utility ── */
.brand-title {
  font-family: var(--font-brand);
  font-weight: 400;
}

.material-symbols-outlined {
  font-family: 'Material Symbols Outlined';
  font-weight: 400;
  font-style: normal;
  font-size: 22px;
  line-height: 1;
  letter-spacing: normal;
  text-transform: none;
  display: inline-block;
  white-space: nowrap;
  direction: ltr;
  font-feature-settings: 'liga';
  -webkit-font-smoothing: antialiased;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
</style>
