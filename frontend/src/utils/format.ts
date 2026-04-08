export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return '—'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function formatMoney(amount: string, currency: string) {
  const numericAmount = Number(amount)
  if (Number.isNaN(numericAmount)) {
    return `${amount} ${currency}`
  }

  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: currency.toUpperCase(),
    maximumFractionDigits: 2,
  }).format(numericAmount)
}
