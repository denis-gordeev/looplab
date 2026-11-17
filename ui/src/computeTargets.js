const TARGET_ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}:([1-9][0-9]{0,4})$/

export function computeOrigin(target) {
  const port = typeof target === 'string' && target.match(TARGET_ID)?.[1]
  if (!port || Number(port) > 65535) return ''
  return `http://127.0.0.1:${port}`
}

export const computePath = target => `/api/compute/${encodeURIComponent(target)}`

export function computeRunHref(target, runId) {
  return `${target ? computeOrigin(target) + '/' : ''}#/run/${encodeURIComponent(runId)}`
}
