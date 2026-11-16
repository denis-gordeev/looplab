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

export function computeCatalog(value) {
  if (!Array.isArray(value?.targets) || value.targets.some(target =>
    !computeOrigin(target?.id) || typeof target?.label !== 'string')) {
    invalidPanelPayload()
  }
  return value.targets
}
import { invalidPanelPayload, isRecord, nullableNumber } from './panelPrimitives.js'


export function gpuPayload(value) {
  if (!isRecord(value) || typeof value.available !== 'boolean'
      || (value.gpus != null && !Array.isArray(value.gpus))) invalidPanelPayload()
  const gpus = value.gpus || []
  for (const gpu of gpus) {
    if (!isRecord(gpu) || !gpu.name || typeof gpu.name !== 'string'
        || ['util', 'mem_used', 'mem_total', 'temp', 'power'].some(key => !nullableNumber(gpu[key]))) {
      invalidPanelPayload()
    }
  }
  if (value.available && !Array.isArray(value.gpus)) invalidPanelPayload()
  return { available: value.available, gpus }
}
