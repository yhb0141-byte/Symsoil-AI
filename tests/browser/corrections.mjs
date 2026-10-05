// Actual browser + API integration, fresh synthetic database for every run.
// A protocol fixture is explicit and does not demonstrate real model quality.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
const { chromium } = await import(process.env.SYMSOIL_PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.SYMSOIL_TEST_URL || 'http://127.0.0.1:8000'
const password = process.env.SYMSOIL_DEMO_PASSWORD
if (!password) throw new Error('Set an explicit synthetic test password')
const fixtureMode = process.env.SYMSOIL_TEST_AI_FIXTURE === '1'
const artifacts = process.env.SYMSOIL_TEST_ARTIFACTS
if (artifacts) await mkdir(artifacts, { recursive: true })
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] })
const contexts = [], errors = [], external = [], passed = []
let lastPage
const title = '合成示例：表达与授权'
async function actor(username, width = 1440) {
  const context = await browser.newContext({ viewport: { width, height: width < 600 ? 844 : 1000 } })
  contexts.push(context)
  const page = await context.newPage()
  page.setDefaultTimeout(15000)
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (!request.url().startsWith(base)) external.push(request.url()) })
  await page.goto(base)
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  const login = page.waitForResponse(r => r.url().endsWith('/auth/login') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '进入工作台', exact: true }).click()
  const proof = (await (await login).json()).csrf_token
  assert.ok(proof)
  await page.getByRole('heading', { name: /^你好，/ }).waitFor()
  return { page, proof }
}
async function get(actor, path) { return actor.page.request.get(`${base}/api/v1${path}`, { headers: { 'X-CSRF-Token': actor.proof } }) }
async function json(actor, path) { const r = await get(actor, path); assert.equal(r.status(), 200, path); return r.json() }
async function nav(page) {
  lastPage = page
  const desktop = page.locator('nav[aria-label="主要功能"]')
  if (await desktop.isVisible()) await desktop.getByRole('button', { name: '查资料', exact: true }).click()
  else {
    await page.locator('nav[aria-label="手机快捷导航"]').getByRole('button', { name: '首页', exact: true }).click()
    await page.getByRole('button', { name: /^查资料/ }).last().click()
  }
  await page.getByRole('heading', { name: '查资料', exact: true }).waitFor()
  await page.getByRole('status').filter({ hasText: '正在读取你有权访问的资料' }).waitFor({ state: 'hidden' })
}
async function tab(page, name) { lastPage = page; await page.locator('nav[aria-label="资料功能"]').getByRole('button', { name: new RegExp(`^${name}`) }).click() }
async function notice(page, text) { await page.getByRole('status').filter({ hasText: text }).waitFor() }
async function close(page) {
  await page.getByRole('status').filter({ hasText: '正在核对本人可见的纠错记录' }).waitFor({ state: 'hidden' })
  await page.getByRole('status').filter({ hasText: '正在读取你有权访问的资料' }).waitFor({ state: 'hidden' })
  await page.getByRole('dialog').getByRole('button', { name: '关闭窗口', exact: true }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
}
async function snapshot(page, name) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, name)
  const dialog = page.getByRole('dialog')
  if (await dialog.count()) { assert.equal(await dialog.evaluate(e => e.scrollWidth > e.clientWidth), false, name); await dialog.evaluate(e => { e.scrollTop = 0 }) }
  if (artifacts) await page.screenshot({ path: `${artifacts}/${name}.png`, fullPage: !(await dialog.count()) })
}
const issue = 'PRIVATE_CORRECTION：合成测试，这段工具与授权说明需要核实。'
async function compose(page, text) {
  await nav(page)
  await tab(page, '当前资料目录')
  await page.locator('.knowledge-document').filter({ has: page.getByRole('heading', { name: title, exact: true }) }).getByRole('button', { name: '查看原文与来源' }).click()
  await page.getByRole('button', { name: '提出资料纠错', exact: true }).click()
  await page.getByRole('dialog', { name: '预览资料纠错 · 仅发给录入者', exact: true }).waitFor()
  await page.getByLabel('我发现的问题', { exact: true }).fill(text)
  await page.getByRole('checkbox', { name: /^我已核对版本和接收人/ }).check()
}
async function send(page) {
  const pending = page.waitForResponse(r => r.url().endsWith('/knowledge-corrections') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '确认发送这条私人纠错', exact: true }).click()
  const item = await (await pending).json()
  await notice(page, '纠错请求已按预览仅发给资料录入者')
  await close(page)
  return item
}
async function inbox(page) {
  await nav(page); await tab(page, '纠错请求')
  await page.getByRole('status').filter({ hasText: '正在核对本人可见的纠错记录' }).waitFor({ state: 'hidden' })
  await page.getByRole('button', { name: '刷新纠错请求', exact: true }).click()
  await page.getByRole('status').filter({ hasText: '正在核对本人可见的纠错记录' }).waitFor({ state: 'hidden' })
}
async function openRequest(page, text) {
  lastPage = page
  await page.locator('.correction-card').filter({ has: page.getByText(text, { exact: true }) }).getByRole('button', { name: '查看双方纠错记录', exact: true }).click()
  await page.getByRole('dialog').getByText(text, { exact: true }).waitFor()
}
async function withdraw(page) {
  await page.getByRole('button', { name: '撤回这次纠错共享', exact: true }).click()
  await page.getByRole('button', { name: '确认撤回这次纠错共享', exact: true }).click()
  await notice(page, '纠错共享已撤回')
  await close(page)
}
try {
  const sender = await actor('lin'), owner = await actor('qiao'), admin = await actor('admin')
  const original = (await json(sender, '/documents')).find(doc => doc.title === title)
  const sourcePath = `/knowledge/${original.id}`
  const originalControl = await json(owner, sourcePath)
  await compose(sender.page, issue)
  assert.equal((await json(sender, '/knowledge-corrections')).items.length, 0)
  await snapshot(sender.page, 'desktop-correction-preview')
  const item = await send(sender.page)
  assert.equal(item.revision_id, original.revision_id)
  assert.equal((await get(admin, `/knowledge-corrections/${item.id}`)).status(), 404)
  assert.equal((await json(admin, '/knowledge-corrections')).counts.incoming, 0)
  assert.deepEqual(await json(owner, sourcePath), originalControl)
  passed.push('核对精确资料与真实录入者，预览不发送；仅双方读取，管理员不可旁观')

  await inbox(owner.page); await openRequest(owner.page, issue)
  await owner.page.getByRole('button', { name: '打开我的资料管理', exact: true }).click()
  await owner.page.getByRole('dialog', { name: '我的资料 · 私人版本与发布版本', exact: true }).waitFor()
  await owner.page.getByRole('dialog').getByRole('button', { name: '另存新的私人版本', exact: true }).click()
  await owner.page.getByLabel('资料完整正文', { exact: true }).fill('合成修订资料：成员核对工具与授权条件。此稿仍需另一位审核人明确审核。')
  await owner.page.getByRole('button', { name: '保存新的私人版本', exact: true }).click()
  await notice(owner.page, '新的私人版本已保存')
  await close(owner.page)
  const draft = await json(owner, sourcePath)
  assert.equal(draft.latest.number, 2); assert.equal(draft.published.number, 1)
  assert.equal((await json(sender, `/documents/${original.id}`)).body, original.body)
  passed.push('从纠错打开本人资料管理，另存私稿保留旧发布，不复制私人问题到正文')

  await inbox(owner.page); await openRequest(owner.page, issue)
  await owner.page.getByLabel('我的核对与回应', { exact: true }).fill('PRIVATE_REPLY：已经另存合成修订私稿，尚待审核，不表示已经生效。')
  await owner.page.getByRole('checkbox', { name: /^我确认只把这段本人回应/ }).check()
  await snapshot(owner.page, 'desktop-correction-response')
  await owner.page.getByRole('button', { name: '发送本人的回应', exact: true }).click()
  await notice(owner.page, '本人的回应已发给请求者')
  await close(owner.page)
  assert.deepEqual(await json(owner, sourcePath), draft)
  assert.equal((await json(sender, `/knowledge-corrections/${item.id}`)).status, 'responded')
  await inbox(sender.page); await openRequest(sender.page, issue)
  await sender.page.getByText('PRIVATE_REPLY：已经另存合成修订私稿，尚待审核，不表示已经生效。', { exact: true }).waitFor()
  await close(sender.page)
  passed.push('本人回应独立授权，状态为已回应，未自动修改或发布资料')

  await tab(owner.page, '我的私人资料')
  await owner.page.locator('.knowledge-own').filter({ has: owner.page.getByRole('heading', { name: title, exact: true }) }).getByRole('button', { name: '核对版本与管理', exact: true }).click()
  await owner.page.getByRole('button', { name: '预览并指定审核人', exact: true }).click()
  await owner.page.getByLabel('指定另一个审核人', { exact: true }).selectOption({ label: '合成管理员' })
  await owner.page.getByRole('checkbox', { name: /^我已核对精确版本/ }).check()
  await owner.page.getByRole('button', { name: '确认此次送审授权', exact: true }).click()
  await notice(owner.page, '仅此精确版本已授权给指定审核人')
  await close(owner.page)
  await nav(admin.page); await tab(admin.page, '指定给我的审核')
  await admin.page.getByRole('button', { name: '核对精确送审版', exact: true }).click()
  await admin.page.getByRole('radio', { name: '来源与授权可核对，通过并按预览受众发布此版', exact: true }).check()
  await admin.page.getByRole('button', { name: '确认通过并发布此精确版本', exact: true }).click()
  await notice(admin.page, '此精确版本已经通过资料审核')
  assert.equal((await get(sender, `/documents/${original.id}?revision_id=${original.revision_id}`)).status(), 404)
  const afterPublish = await json(sender, `/knowledge-corrections/${item.id}`)
  assert.equal(afterPublish.source, null); assert.equal(afterPublish.revision_id, original.revision_id)
  assert.equal((await get(admin, `/knowledge-corrections/${item.id}`)).status(), 404)
  await inbox(sender.page); await openRequest(sender.page, issue)
  await sender.page.getByRole('dialog').getByRole('heading', { name: '关联版本当前不可查阅', exact: true }).waitFor()
  assert.equal(await sender.page.getByRole('button', { name: '重新核对关联原文', exact: true }).count(), 0)
  await snapshot(sender.page, 'desktop-superseded-correction')
  await withdraw(sender.page)
  assert.equal((await get(owner, `/knowledge-corrections/${item.id}`)).status(), 404)
  assert.equal((await json(owner, '/knowledge-corrections')).counts.incoming, 0)
  assert.equal((await json(sender, `/knowledge-corrections/${item.id}`)).status, 'withdrawn')
  passed.push('新版独立审核不带出私人纠错；原请求保留旧版身份，撤回停止录入者读取')

  const secondText = 'SECOND_PRIVATE_ISSUE：合成测试，回应前撤回共享。'
  await compose(sender.page, secondText); const second = await send(sender.page)
  await inbox(owner.page); await openRequest(owner.page, secondText)
  await openRequest(sender.page, secondText); await withdraw(sender.page)
  await owner.page.getByLabel('我的核对与回应', { exact: true }).fill('迟到回应不能提交')
  await owner.page.getByRole('checkbox', { name: /^我确认只把这段本人回应/ }).check()
  await owner.page.getByRole('button', { name: '发送本人的回应', exact: true }).click()
  await owner.page.getByRole('alert').filter({ hasText: '记录不可访问' }).waitFor()
  assert.equal((await owner.page.locator('body').innerText()).includes(secondText), false)
  assert.equal((await json(sender, `/knowledge-corrections/${second.id}`)).response, null)
  await close(owner.page)
  passed.push('对方撤回后迟到回应被拒，页面清除旧私人正文，不复活共享')

  const mobile = await actor('lin', 390)
  await compose(mobile.page, 'MOBILE_PRIVATE_ISSUE：合成手机纠错。')
  await snapshot(mobile.page, 'mobile-correction-preview')
  await send(mobile.page)
  await openRequest(mobile.page, 'MOBILE_PRIVATE_ISSUE：合成手机纠错。')
  await snapshot(mobile.page, 'mobile-correction-detail')
  await withdraw(mobile.page)
  await mobile.page.getByRole('button', { name: '退出账号', exact: true }).click()
  await mobile.page.getByRole('button', { name: '进入工作台', exact: true }).waitFor()
  assert.equal((await mobile.page.locator('body').innerText()).includes('MOBILE_PRIVATE_ISSUE'), false)
  passed.push('390像素手机预览、记录和撤回无溢出；退出清除纠错内容')
  assert.deepEqual(errors, []); assert.deepEqual(external, [])
  console.log(JSON.stringify({ passed, browser: browser.version(), errors, external, syntheticOnly: true }, null, 2))
} catch (error) {
  if (lastPage) { await snapshot(lastPage, 'failure').catch(() => {}); console.error((await lastPage.locator('body').innerText()).slice(-6000)) }
  throw error
} finally { for (const context of contexts) await context.close(); await browser.close() }
