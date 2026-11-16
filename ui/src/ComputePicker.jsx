import React from 'react'
import { get } from './apiClient.js'
import { computeCatalog, computePath, gpuPayload } from './computeTargets.js'
import { useScopedResource } from './useScopedResource.js'
import { uiMessage, uiText, useUILanguage } from './uiLanguage.js'

export function useComputeTargets() {
  return useScopedResource(signal => get('/api/compute', { signal }).then(computeCatalog),
    { scope: 'compute', timeout: 5000 })
}

export function computeGpuPath(target) {
  return target ? computePath(target) + '/gpu' : '/api/gpu'
}

export function ComputePicker({ catalog, target, onChange, disabled }) {
  useUILanguage()
  const targets = catalog.data || []
  const available = !target || targets.some(option => option.id === target)

  return <label>
    <span>{uiText('Compute target')} </span>
    <select value={target} disabled={disabled} onChange={event => onChange(event.target.value)}>
      <option value="">{uiText('Local (this LoopLab server)')}</option>
      {!available && <option value={target}>{target}</option>}
      {targets.map(option => <option key={option.id} value={option.id}>
        {uiMessage('{0} · SSH', [option.label])}
      </option>)}
    </select>
  </label>
}

export function LaunchComputePicker({ target, onChange, disabled }) {
  useUILanguage()
  const catalog = useComputeTargets()
  const telemetry = useScopedResource(signal => get(computeGpuPath(target), { signal }).then(gpuPayload),
    { scope: target || 'local', timeout: 6000 })
  const { data, status } = telemetry
  const gpus = data?.available ? data.gpus : []
  return <div>
    <ComputePicker catalog={catalog} target={target} onChange={onChange} disabled={disabled} />
    <button type="button" className="btn xs" disabled={!!telemetry.pending}
      onClick={() => { catalog.retry(); telemetry.retry() }}>{uiText('Test connection')}</button>
    <div role="status" className="asst-launch-help">
      {(catalog.status === 'error' || catalog.status === 'stale')
        && <div>{uiText('Compute targets could not be loaded.')}</div>}
      {status === 'error' || status === 'stale'
        ? uiText('GPU telemetry unavailable. Check the selected server connection.')
        : !data ? uiText('Checking GPU telemetry…')
        : !gpus.length ? uiText('No GPU devices reported.')
        : <ul>{gpus.map((gpu, index) => <li key={index}>
          {gpu.name}{Number.isFinite(gpu.mem_used) && Number.isFinite(gpu.mem_total)
            ? uiMessage(' · {0} / {1} MiB free VRAM', [
              Math.max(0, gpu.mem_total - gpu.mem_used), gpu.mem_total,
            ])
            : ''}
        </li>)}</ul>}
    </div>
  </div>
}
