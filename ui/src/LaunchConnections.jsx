import { uiMessage } from './uiLanguage.js'
import React from 'react'
import { get } from './apiClient.js'
import { computePath } from './computeTargets.js'
import { useScopedResource } from './useScopedResource.js'
import { uiText, useUILanguage } from './uiLanguage.js'

const agentNames = {
  default: 'LoopLab',
  codex: 'Codex',
  claude: 'Claude Code',
  opencode: 'OpenCode',
  aider: 'Aider',
  goose: 'Goose',
  continue: 'Continue',
}

function connectionOptions(data) {
  if (!data || !Array.isArray(data.profiles) || data.profiles.some(name => typeof name !== 'string')
      || !Object.hasOwn(agentNames, data.developer_backend) || !data.agents) {
    throw new Error(uiText('Connection list unavailable.'))
  }
  return data
}

export default function LaunchConnections({ target, settings, onChange, disabled }) {
  useUILanguage()
  const path = target ? computePath(target) : '/api/compute'
  const resource = useScopedResource(signal => get(path + '/connections', { signal }).then(connectionOptions),
    { scope: path, timeout: 6500 })
  const { data } = resource
  const profile = settings.llm_profile ?? ''
  const backend = settings.developer_backend ?? ''
  const agent = backend || data?.developer_backend
  const missingProfile = profile && !data?.profiles.includes(profile)
  return <fieldset className="asst-launch-driver" disabled={disabled}>
    <legend>{uiText('Models and agents')}</legend>
    <label>{uiText('LLM connection')} <select value={profile} onChange={event =>
      onChange('llm_profile', event.target.value)}>
      <option value="">{uiText('Use server settings')}</option>
      {missingProfile && <option value={profile}>{profile}</option>}
      {data?.profiles.map(name => <option key={name} value={name}>{name}</option>)}
    </select></label>
    <label>{uiText('Developer backend')} <select value={backend} onChange={event =>
      onChange('developer_backend', event.target.value)}>
      <option value="">{uiText('Use server settings')}</option>
      {Object.entries(agentNames).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
    </select></label>
    {agent === 'opencode' && <label>{uiText('OpenCode provider/model')} <input type="text"
      value={settings.opencode_model ?? ''} placeholder={(data?.opencode_model || uiText('provider/model'))}
      onChange={event => onChange('opencode_model', event.target.value)} /></label>}
    <button type="button" className="btn xs" disabled={!!resource.pending}
      onClick={() => resource.retry()}>{uiText('Check CLI installation')}</button>
    <p className="asst-launch-help" role="status">
      {resource.status === 'error' || resource.status === 'stale'
        ? uiText('Connection list unavailable.')
        : data && agent && agent !== 'default'
          ? (data.agents[agent] === true
            ? uiText('CLI found on the selected server. Sign in through that CLI before running.')
            : uiText('CLI not found on the selected server.'))
          : null}
    </p>
  </fieldset>
}
