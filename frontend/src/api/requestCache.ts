export function createSingleFlightByKey<TKey, TValue>() {
  const inflight = new Map<TKey, Promise<TValue>>()

  return async (key: TKey, loader: () => Promise<TValue>) => {
    const existing = inflight.get(key)
    if (existing) {
      return existing
    }

    const request = loader().finally(() => {
      inflight.delete(key)
    })

    inflight.set(key, request)
    return request
  }
}

export function createCachedSingleFlight<TValue>() {
  let inflight: Promise<TValue> | null = null
  let cached: TValue | null = null

  return async (loader: () => Promise<TValue>) => {
    if (cached) {
      return cached
    }

    if (inflight) {
      return inflight
    }

    inflight = loader()
      .then((value) => {
        cached = value
        return value
      })
      .finally(() => {
        inflight = null
      })

    return inflight
  }
}
