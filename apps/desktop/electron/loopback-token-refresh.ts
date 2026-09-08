/**
 * A URL-mode desktop launched through a loopback SSH tunnel can safely learn
 * the dashboard token served by that same loopback endpoint. The dashboard
 * rotates its ephemeral token on restart, while an already-running desktop
 * otherwise keeps the launch-time token and loops on HTTP 401 forever.
 *
 * Keep this deliberately narrow: only env-selected, token-authenticated,
 * loopback remotes qualify. Saved internet-facing remotes and OAuth gateways
 * must never replace their configured credentials from public page content.
 */

interface RefreshableConnection {
  authMode?: string
  baseUrl?: string
  source?: string
  token?: unknown
}

interface TokenRefreshOptions {
  resolveToken: (baseUrl: string, fallbackToken: string) => Promise<unknown>
}

const refreshes = new WeakMap<object, Promise<string | null>>()

export function isUnauthorizedResponse(error: unknown): boolean {
  if (error && typeof error === 'object' && Number((error as { statusCode?: unknown }).statusCode) === 401) {
    return true
  }

  const message = error instanceof Error ? error.message : String(error ?? '')

  return /^401:/.test(message)
}

export function isLoopbackUrl(rawUrl: unknown): boolean {
  try {
    const hostname = new URL(String(rawUrl || '')).hostname.toLowerCase()

    return hostname === '127.0.0.1' || hostname === '[::1]' || hostname === '::1' || hostname === 'localhost'
  } catch {
    return false
  }
}

export function canRefreshLoopbackSessionToken(connection: RefreshableConnection, error: unknown): boolean {
  return canDiscoverLoopbackSessionToken(connection) && isUnauthorizedResponse(error)
}

export function canDiscoverLoopbackSessionToken(connection: RefreshableConnection): boolean {
  return (
    connection?.source === 'env' &&
    connection?.authMode === 'token' &&
    typeof connection?.token === 'string' &&
    Boolean(connection.token) &&
    isLoopbackUrl(connection.baseUrl)
  )
}

/**
 * Reconcile one served token per descriptor at a time. This may run during
 * boot before an authenticated request fails: readiness endpoints can be
 * public, and the renderer needs the current token embedded in its initial
 * WebSocket URL. Returns null when the route is ineligible or unchanged.
 */
export async function reconcileLoopbackSessionToken(
  connection: RefreshableConnection,
  options: TokenRefreshOptions
): Promise<string | null> {
  if (!canDiscoverLoopbackSessionToken(connection)) {
    return null
  }

  const key = connection as object
  const pending = refreshes.get(key)

  if (pending) {
    return pending
  }

  const fallbackToken = connection.token as string

  const refresh = Promise.resolve(options.resolveToken(connection.baseUrl as string, fallbackToken))
    .then(token => {
      const resolved = typeof token === 'string' ? token.trim() : ''

      return resolved && resolved !== fallbackToken ? resolved : null
    })
    .finally(() => {
      if (refreshes.get(key) === refresh) {
        refreshes.delete(key)
      }
    })

  refreshes.set(key, refresh)

  return refresh
}

/**
 * HTTP requests only attempt discovery after a real 401. Boot code should use
 * reconcileLoopbackSessionToken directly before publishing the descriptor.
 */
export async function refreshLoopbackSessionToken(
  connection: RefreshableConnection,
  error: unknown,
  options: TokenRefreshOptions
): Promise<string | null> {
  if (!canRefreshLoopbackSessionToken(connection, error)) {
    return null
  }

  return reconcileLoopbackSessionToken(connection, options)
}
