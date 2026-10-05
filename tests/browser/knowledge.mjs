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
const title = '合成资料 ZXTOOLS 清理工具核对'
const firstBody = '合成资料 ZXTOOLS：清理工具需由本人核对。\n合成条件：参与前说明时间、责任和工具来源。\n<script>throw new Error("TEXT_ONLY")</script>'
const nextBody = '合成资料 ZXTOOLS：新版清理工具需核对完好状态。\n合成条件：尚未产生任务接受或决定批准。'
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
async function manage(page) {
  await tab(page, '我的私人资料')
  await page.locator('.knowledge-own').filter({ has: page.getByRole('heading', { name: title, exact: true }) }).getByRole('button', { name: '核对版本与管理', exact: true }).click()
  await page.getByRole('dialog', { name: '我的资料 · 私人版本与发布版本', exact: true }).waitFor()
}
async function submit(page) {
  await page.getByRole('button', { name: '预览并指定审核人', exact: true }).click()
  await page.getByLabel(/^指定另一个审核人/).selectOption({ label: '林禾 · 合成主持人' })
  await page.getByRole('checkbox', { name: /^我已核对精确版本/ }).check()
  await snapshot(page, 'desktop-submit-preview')
  await page.getByRole('button', { name: '确认此次送审授权', exact: true }).click()
  await notice(page, '仅此精确版本已授权给指定审核人')
  await close(page)
}
async function approve(page) {
  await nav(page)
  await tab(page, '指定给我的审核')
  await page.locator('.knowledge-review').filter({ has: page.getByRole('heading', { name: title, exact: true }) }).getByRole('button', { name: '核对精确送审版', exact: true }).click()
  await page.getByRole('radio', { name: '来源与授权可核对，通过并按预览受众发布此版', exact: true }).check()
  await page.getByLabel('审核说明（可选）', { exact: true }).fill('合成测试：只核对资料，不批准任何任务。')
  await snapshot(page, 'desktop-review-preview')
  await page.getByRole('button', { name: '确认通过并发布此精确版本', exact: true }).click()
  await notice(page, '此精确版本已经通过资料审核')
}
try {
  const qiao = await actor('qiao'), lin = await actor('lin'), admin = await actor('admin')
  const initialLinCount = (await json(lin, '/documents')).length
  const initialAdminCount = (await json(admin, '/documents')).length
  const initialMine = await json(qiao, '/knowledge/mine')
  const initialTopic = await json(lin, '/topics')
  const initialTasks = await json(qiao, '/invitations')
  await nav(qiao.page); await tab(qiao.page, '我的私人资料')
  await qiao.page.getByRole('button', { name: '新增私人文字资料', exact: true }).click()
  await qiao.page.getByLabel('资料标题', { exact: true }).fill(title)
  await qiao.page.getByLabel('资料分类', { exact: true }).fill('合成参与方法')
  await qiao.page.getByLabel('本地读取 UTF-8 文字（可选）', { exact: true }).setInputFiles({ name: 'synthetic.md', mimeType: 'text/markdown', buffer: Buffer.from(firstBody, 'utf8') })
  await notice(qiao.page, '尚未上传或保存')
  assert.deepEqual(await json(qiao, '/knowledge/mine'), initialMine)
  assert.equal(await qiao.page.getByLabel('资料完整正文', { exact: true }).inputValue(), firstBody)
  await qiao.page.getByLabel('来源', { exact: true }).fill('合成来源 SOURCE_PRIVATE：测试人员自己编写')
  await qiao.page.getByLabel('授权依据与使用边界', { exact: true }).fill('合成授权：仅用于合成验证，不含真实人物资料。')
  await qiao.page.getByLabel('本次用途', { exact: true }).fill('合成工具条件核对')
  await qiao.page.getByLabel('维护人或人工联系路径', { exact: true }).fill('合成维护人：乔雨')
  await qiao.page.getByRole('radio', { name: /^明确选择的固定名单/ }).check()
  await qiao.page.getByRole('checkbox', { name: '林禾 · 合成主持人', exact: true }).check()
  const createdResponse = qiao.page.waitForResponse(r => r.url().endsWith('/knowledge') && r.request().method() === 'POST')
  await qiao.page.getByRole('button', { name: '保存私人文字资料', exact: true }).click()
  const created = await (await createdResponse).json(), id = created.id
  await notice(qiao.page, '私人资料已保存')
  assert.equal((await get(lin, `/knowledge/${id}`)).status(), 404)
  assert.equal((await get(admin, `/knowledge/${id}`)).status(), 404)
  assert.equal((await json(lin, '/documents')).length, initialLinCount)
  assert.deepEqual(await json(lin, '/knowledge/reviews'), [])
  passed.push('UTF-8文件只在本页读取，私稿来源、标题、数量与审核队列均隔离')
  await submit(qiao.page)
  assert.equal((await json(lin, '/knowledge/reviews'))[0].revision.body, firstBody)
  assert.deepEqual(await json(admin, '/knowledge/reviews'), [])
  await approve(lin.page)
  let detail = await json(qiao, `/knowledge/${id}`)
  const firstRevision = detail.published.id
  assert.equal(detail.publication_active, true)
  assert.equal((await json(lin, '/documents')).length, initialLinCount + 1)
  assert.equal((await json(admin, '/documents')).length, initialAdminCount)
  assert.equal((await get(admin, `/documents/${id}`)).status(), 404)
  passed.push('本人指定另一审核人，精确版本发布后仅固定名单及作者可读')

  await tab(lin.page, '当前资料目录')
  await lin.page.getByLabel('搜索社区资料', { exact: true }).fill('ZXTOOLS')
  await lin.page.getByRole('button', { name: '查找资料', exact: true }).click()
  await lin.page.getByText('当前可读匹配资料 1 份。', { exact: false }).waitFor()
  await lin.page.getByRole('button', { name: '查看原文与来源' }).click()
  await lin.page.getByText('<script>throw new Error("TEXT_ONLY")</script>', { exact: true }).waitFor()
  await snapshot(lin.page, 'desktop-source-located')
  await close(lin.page)
  await tab(lin.page, '有来源问答')
  await lin.page.getByLabel('我的问题', { exact: true }).fill('ZXTOOLS')
  const answerResponse = lin.page.waitForResponse(r => r.url().endsWith('/knowledge/answers') && r.request().method() === 'POST')
  await lin.page.getByRole('button', { name: '查找可核对的资料摘录', exact: true }).click()
  const extracted = await (await answerResponse).json()
  assert.equal(extracted.mode, 'extract'); assert.ok(extracted.citations.length)
  assert.ok(extracted.citations.every(c => c.document_id === id && c.revision_id === firstRevision))
  await lin.page.getByText('资料摘录，非模型回答', { exact: true }).waitFor()
  await lin.page.getByRole('button', { name: '查看此引用的精确原文' }).first().click()
  await lin.page.getByText(/^引用定位：第/).waitFor()
  assert.ok(await lin.page.locator('.knowledge-source-lines .highlighted').count())
  await snapshot(lin.page, 'desktop-citation-source')
  await close(lin.page)
  passed.push('字面关键词、非模型摘录、真实版本与原始行号引用，正文仅作文字显示')

  if (fixtureMode) {
    await lin.page.getByRole('checkbox', { name: /^我主动使用已就绪的本地模型/ }).check()
    const generatedResponse = lin.page.waitForResponse(r => r.url().endsWith('/knowledge/answers') && r.request().method() === 'POST')
    await lin.page.getByRole('button', { name: '依据资料请求本地回答', exact: true }).click()
    const generated = await (await generatedResponse).json()
    assert.equal(generated.mode, 'local_model'); assert.equal(generated.model, 'symsoil-synthetic-test:latest')
    assert.ok(generated.citations.every(c => c.document_id === id && c.revision_id === firstRevision))
    await lin.page.getByText(/合成问答协议样本/).waitFor()
    await snapshot(lin.page, 'desktop-synthetic-model-answer')
    passed.push('显式合成HTTP协议经过真实本地适配器，引用由服务器恢复，无真实推理质量结论')
  } else {
    assert.equal(await lin.page.getByRole('checkbox', { name: /^我主动使用已就绪的本地模型/ }).isDisabled(), true)
    passed.push('模型默认关闭，资料审核与摘录全流程仍可用')
  }

  await manage(qiao.page)
  await qiao.page.getByRole('dialog').getByRole('button', { name: '另存新的私人版本', exact: true }).click()
  await qiao.page.getByLabel('资料完整正文', { exact: true }).fill(nextBody)
  await qiao.page.getByRole('button', { name: '保存新的私人版本', exact: true }).click()
  await notice(qiao.page, '新的私人版本已保存')
  detail = await json(qiao, `/knowledge/${id}`)
  assert.notEqual(detail.latest.id, detail.published.id)
  assert.equal((await json(lin, `/documents/${id}`)).body, firstBody)
  assert.deepEqual(await json(lin, '/knowledge/reviews'), [])
  await submit(qiao.page); await approve(lin.page)
  detail = await json(qiao, `/knowledge/${id}`)
  assert.equal(detail.published.number, 2)
  assert.equal((await get(lin, `/documents/${id}?revision_id=${firstRevision}`)).status(), 404)
  assert.equal((await json(lin, `/documents/${id}`)).body, nextBody)
  passed.push('另存私稿保留旧发布版，新版重新核对发布后旧版本引用拒绝读取')

  const mobile = await actor('lin', 390)
  await nav(mobile.page); await tab(mobile.page, '有来源问答')
  await mobile.page.getByLabel('我的问题', { exact: true }).fill('ZXTOOLS')
  await mobile.page.getByRole('button', { name: '查找可核对的资料摘录', exact: true }).click()
  await mobile.page.getByRole('button', { name: '查看此引用的精确原文' }).first().click()
  await snapshot(mobile.page, 'mobile-citation-source')
  await close(mobile.page)
  passed.push('390像素手机摘录与精确原文窗口无水平溢出')

  await manage(qiao.page)
  await qiao.page.getByRole('dialog').getByRole('button', { name: '另存新的私人版本', exact: true }).click()
  await qiao.page.getByLabel('资料完整正文', { exact: true }).fill(`${nextBody}\n合成第三版：本次仅测试撤回送审，不替换发布。`)
  await qiao.page.getByRole('button', { name: '保存新的私人版本', exact: true }).click()
  await notice(qiao.page, '新的私人版本已保存')
  await submit(qiao.page); await manage(qiao.page)
  await qiao.page.getByRole('button', { name: '撤回本次送审', exact: true }).click()
  await notice(qiao.page, '本次送审授权已经撤回')
  assert.deepEqual(await json(lin, '/knowledge/reviews'), [])
  assert.equal((await json(qiao, `/knowledge/${id}`)).publication_active, true)
  await qiao.page.getByRole('button', { name: '收紧当前发布受众', exact: true }).click()
  await qiao.page.getByRole('checkbox', { name: '林禾 · 合成主持人', exact: true }).uncheck()
  await qiao.page.getByRole('button', { name: '确认只收紧当前受众', exact: true }).click()
  await notice(qiao.page, '当前发布资料的受众已经收紧')
  assert.equal((await get(lin, `/documents/${id}`)).status(), 404)
  assert.equal((await json(lin, '/documents')).length, initialLinCount)
  await mobile.page.getByRole('button', { name: '查看此引用的精确原文' }).first().click()
  await mobile.page.getByRole('alert').filter({ hasText: '旧摘录与回答已清除' }).waitFor()
  assert.equal(await mobile.page.locator('.knowledge-answer-result').count(), 0)
  passed.push('撤回送审保留发布；收紧为空仅作者可读，旧引用失败清除页面结果')

  await qiao.page.getByRole('button', { name: '撤下当前发布资料', exact: true }).click()
  await qiao.page.getByRole('button', { name: '确认撤下当前发布版', exact: true }).click()
  await notice(qiao.page, '当前发布版已经撤下')
  detail = await json(qiao, `/knowledge/${id}`)
  assert.equal(detail.publication_active, false); assert.equal(detail.audience, null)
  assert.equal(detail.published.number, 2)
  assert.equal((await get(qiao, `/documents/${id}`)).status(), 404)
  assert.equal(await qiao.page.getByRole('button', { name: '撤下当前发布资料', exact: true }).count(), 0)
  assert.deepEqual(await json(lin, '/topics'), initialTopic)
  assert.deepEqual(await json(qiao, '/invitations'), initialTasks)
  passed.push('撤下停止全文与引用但保留本人版本历史，不改变独立立场或任务')
  assert.deepEqual(errors, [], 'browser exceptions'); assert.deepEqual(external, [], 'external resource requests')
  console.log(JSON.stringify({ passed, fixtureMode, realModelInferenceTested: false, browser: browser.version(), errors, external }, null, 2))
} catch (error) {
  if (lastPage) { await snapshot(lastPage, 'failure').catch(() => {}); console.error((await lastPage.locator('body').innerText()).slice(-7000)) }
  throw error
} finally { for (const context of contexts) await context.close(); await browser.close() }
