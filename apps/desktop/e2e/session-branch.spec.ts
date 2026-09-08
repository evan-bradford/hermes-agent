import { execFileSync } from 'node:child_process'
import path from 'node:path'

import {
  buildAppEnv,
  createSandbox,
  launchDesktop,
  type MockBackendFixture,
  waitForAppReady,
  writeEnvFile,
  writeMockProviderConfig
} from './fixtures'
import { startMockServer } from './mock-server'
import { RealSessionBuilder } from './real-session-builder'
import { expect, test } from './test'

let parentSessionId = ''

const SESSION_LABEL = 'E2E persisted conversation branch parent'

async function setupSeededBackend(): Promise<MockBackendFixture> {
  const mock = await startMockServer()
  const sandbox = createSandbox('session-branch')

  writeMockProviderConfig(sandbox.hermesHome, mock.url)
  writeEnvFile(sandbox.hermesHome)

  const builder = await RealSessionBuilder.start(sandbox.hermesHome)

  try {
    parentSessionId = (await builder.createSession({ title: SESSION_LABEL, turns: [SESSION_LABEL] })).sessionId
  } finally {
    await builder.close()
  }

  const { app, page } = await launchDesktop(buildAppEnv(sandbox))

  return {
    app,
    page,
    mock,
    mockUrl: mock.url,
    sandbox,
    cleanup: async () => {
      await app.close()
      await mock.close()
      sandbox.cleanup()
    }
  }
}

test.describe('persisted session branching', () => {
  let fixture: MockBackendFixture

  test.beforeAll(async () => {
    fixture = await setupSeededBackend()
    await waitForAppReady(fixture, 120_000)
  })

  test.afterAll(async () => {
    await fixture?.cleanup()
  })

  test('branches from the visible session-row action and renders the nested child', async () => {
    const parentLabel = fixture.page.getByText(SESSION_LABEL, { exact: true }).first()

    await expect(parentLabel).toBeVisible({ timeout: 30_000 })

    const parentRow = parentLabel.locator('xpath=ancestor::div[contains(@class, "row-hover")]').first()

    await parentRow.hover()
    await parentRow.getByRole('button', { name: 'Session actions' }).click()
    await fixture.page.getByRole('menuitem', { name: 'Branch', exact: true }).click()

    const childLabel = fixture.page.getByText(/draft: branch #\d+/i).first()

    await expect(childLabel).toBeVisible({ timeout: 30_000 })
    await expect(parentLabel).toBeVisible()
    // The child must survive hydration: an optimistic row alone is not a branch.
    const readChildren = () =>
      JSON.parse(
        execFileSync(
          path.resolve(import.meta.dirname, '../../../.venv/bin/python'),
          [
            '-c',
            'import json,sqlite3,sys; c=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True); print(json.dumps(c.execute("select id, parent_session_id, message_count from sessions where parent_session_id = ?",(sys.argv[2],)).fetchall()))',
            path.join(fixture.sandbox.hermesHome, 'state.db'),
            parentSessionId
          ],
          { encoding: 'utf8' }
        )
      ) as Array<[string, string, number]>
    await expect.poll(() => readChildren().length).toBe(1)
    expect(readChildren()[0][2]).toBeGreaterThan(0)
  })
})
