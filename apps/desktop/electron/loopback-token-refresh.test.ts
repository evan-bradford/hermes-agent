import assert from 'node:assert/strict'

import { test } from 'vitest'

import {
  canDiscoverLoopbackSessionToken,
  canRefreshLoopbackSessionToken,
  isLoopbackUrl,
  isUnauthorizedResponse,
  reconcileLoopbackSessionToken,
  refreshLoopbackSessionToken
} from './loopback-token-refresh'

const eligible = () => ({
  authMode: 'token',
  baseUrl: 'http://localhost:9119',
  source: 'env',
  token: 'old-token'
})

test('recognizes loopback hosts without accepting lookalike domains', () => {
  assert.equal(isLoopbackUrl('http://127.0.0.1:9119'), true)
  assert.equal(isLoopbackUrl('http://[::1]:9119'), true)
  assert.equal(isLoopbackUrl('http://localhost:9119'), true)
  assert.equal(isLoopbackUrl('https://localhost.example.com'), false)
  assert.equal(isLoopbackUrl('not a url'), false)
})

test('recognizes structured and legacy unauthorized errors only', () => {
  assert.equal(isUnauthorizedResponse(new Error('401: {"detail":"Unauthorized"}')), true)
  assert.equal(isUnauthorizedResponse(Object.assign(new Error('rejected'), { statusCode: 401 })), true)
  assert.equal(isUnauthorizedResponse(new Error('403: forbidden')), false)
})

test('limits refresh to env-selected token auth over loopback', () => {
  assert.equal(canDiscoverLoopbackSessionToken(eligible()), true)
  assert.equal(canRefreshLoopbackSessionToken(eligible(), new Error('401: rejected')), true)
  assert.equal(canDiscoverLoopbackSessionToken({ ...eligible(), source: 'settings' }), false)
  assert.equal(canRefreshLoopbackSessionToken({ ...eligible(), source: 'settings' }, new Error('401: rejected')), false)
  assert.equal(
    canRefreshLoopbackSessionToken({ ...eligible(), baseUrl: 'https://gateway.example' }, new Error('401: rejected')),
    false
  )
  assert.equal(canRefreshLoopbackSessionToken(eligible(), new Error('500: broken')), false)
})

test('reconciles the served token during boot without waiting for a 401', async () => {
  assert.equal(
    await reconcileLoopbackSessionToken(eligible(), {
      resolveToken: async () => 'boot-token'
    }),
    'boot-token'
  )
  assert.equal(
    await reconcileLoopbackSessionToken({ ...eligible(), source: 'settings' }, {
      resolveToken: async () => 'must-not-be-used'
    }),
    null
  )
})

test('returns a changed served token and ignores an unchanged token', async () => {
  assert.equal(
    await refreshLoopbackSessionToken(eligible(), new Error('401: rejected'), {
      resolveToken: async () => 'new-token'
    }),
    'new-token'
  )
  assert.equal(
    await refreshLoopbackSessionToken(eligible(), new Error('401: rejected'), {
      resolveToken: async () => 'old-token'
    }),
    null
  )
})

test('coalesces concurrent refreshes for one connection descriptor', async () => {
  const connection = eligible()
  let calls = 0
  let release!: (value: string) => void

  const resolved = new Promise<string>(resolve => {
    release = resolve
  })

  const options = {
    resolveToken: async () => {
      calls += 1

      return resolved
    }
  }

  const first = refreshLoopbackSessionToken(connection, new Error('401: rejected'), options)
  const second = refreshLoopbackSessionToken(connection, new Error('401: rejected'), options)
  release('rotated-token')

  assert.deepEqual(await Promise.all([first, second]), ['rotated-token', 'rotated-token'])
  assert.equal(calls, 1)
})
