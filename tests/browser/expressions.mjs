// Real UI + local HTTP integration, isolated synthetic database only.
// SYMSOIL_TEST_AI_FIXTURE=1 uses an explicitly synthetic Ollama protocol server.
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
let lastPage = null
const topicTitle = '合成演示：周末公共场地工作坊'
const sourceText = '合成私人原话 SOURCE_ONLY：我暂不接受清理劳动。我想先核对工具和时间。'
const contextText = '合成私人语境 CONTEXT_ONLY：这不是公开讨论内容。'
const publishedText = '合成本人转述 PUBLISHED_ONLY：请先说明清理工具、时间与责任；我尚未接受任务。'
async function actor(username, width = 1440) {
  const context = await browser.newContext({ viewport: { width, height: width < 600 ? 844 : 1000 } })
  contexts.push(context)
  const page = await context.newPage()
  page.setDefaultTimeout(15000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('request', req => { if (!req.url().startsWith(base)) external.push(req.url()) })
  await page.goto(base)
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  const login = page.waitForResponse(r => r.url().endsWith('/auth/login') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '进入工作台', exact: true }).click()
  const proof = (await (await login).json()).csrf_token
  assert.ok(proof, 'login supplies in-memory proof')
  await page.getByRole('heading', { name: /^你好，/ }).waitFor()
  return { page, proof }
}
async function get(actor, path) {
  return actor.page.request.get(`${base}/api/v1${path}`, { headers: { 'X-CSRF-Token': actor.proof } })
}
async function json(actor, path) {
  const r = await get(actor, path)
  assert.equal(r.status(), 200, path)
  return r.json()
}
async function nav(page, name) {
  lastPage = page
  const desktop = page.locator('nav[aria-label="主要功能"]')
  if (await desktop.isVisible()) await desktop.getByRole('button', { name, exact: true }).click()
  else {
    await page.locator('nav[aria-label="手机快捷导航"]').getByRole('button', { name: '首页', exact: true }).click()
    await page.getByRole('heading', { name: /^你好，/ }).waitFor()
    await page.getByRole('button', { name: new RegExp(`^${name}`) }).last().click()
  }
  await page.getByRole('heading', { name, exact: true }).waitFor()
}
async function topic(page) {
  await nav(page, '看议题')
  await page.getByRole('button', { name: '查看观点与方案' }).first().click()
  await page.getByRole('heading', { name: topicTitle, exact: true }).waitFor()
}
async function notice(page, text) { await page.getByRole('status').filter({ hasText: text }).waitFor() }
async function snapshot(page, name) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `page overflow: ${name}`)
  const dialog = page.getByRole('dialog')
  if (await dialog.count()) {
    assert.equal(await dialog.evaluate(e => e.scrollWidth > e.clientWidth), false, `dialog overflow: ${name}`)
    await dialog.evaluate(e => { e.scrollTop = 0 })
  }
  if (artifacts) await page.screenshot({ path: `${artifacts}/${name}.png`, fullPage: !(await dialog.count()) })
}
async function createSource(page, title, text) {
  await nav(page, '说想法')
  await page.getByRole('button', { name: '写一个私稿', exact: true }).click()
  await page.getByLabel('想法标题').fill(title)
  await page.getByLabel('我的原话', { exact: true }).fill(text)
  const response = page.waitForResponse(r => r.url().endsWith('/utterances') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '保存私人原话', exact: true }).click()
  const created = await (await response).json()
  await notice(page, '私稿已保存')
  return created
}
async function review(page, title) {
  await page.locator('article').filter({ has: page.getByRole('heading', { name: title, exact: true }) }).getByRole('button', { name: '原话与转述核对', exact: true }).click()
  await page.getByRole('dialog', { name: '原话与候选转述 · 仅本人可见', exact: true }).waitFor()
}
async function saveCandidate(page, kind, text, context = '') {
  lastPage = page
  await page.getByRole('button', { name: '手写私人候选（最多两种）', exact: true }).click()
  await page.getByLabel(/^候选类型/).selectOption(kind)
  await page.getByLabel('候选正文', { exact: true }).fill(text)
  await page.getByLabel('本人提供的背景语境（仅本人可见）', { exact: true }).fill(context)
  await page.getByLabel('目标表达语境（仅本人可见）', { exact: true }).fill('合成目标 TARGET_ONLY')
  await page.getByLabel('用途（仅本人可见）', { exact: true }).fill('合成用途 PURPOSE_ONLY')
  await page.getByRole('button', { name: '保存候选，稍后本人核对', exact: true }).click()
  await notice(page, '私人候选已保存')
}
try {
  const qiao = await actor('qiao'), lin = await actor('lin'), admin = await actor('admin')
  const topicId = (await json(lin, '/topics'))[0].id
  const title = '合成跨语境表达测试'
  const source = await createSource(qiao.page, title, sourceText)
  const detailPath = `/utterances/${source.id}/expression`
  await review(qiao.page, title)
  await qiao.page.getByRole('button', { name: '本人确认这版原话准确', exact: true }).click()
  await notice(qiao.page, '尚未因此增加分享权限')
  await saveCandidate(qiao.page, 'everyday', publishedText, contextText)
  await saveCandidate(qiao.page, 'discussion', '合成未分享候选 OTHER_CANDIDATE_ONLY：清理条件仍待核实。')
  assert.equal(await qiao.page.getByRole('button', { name: '手写私人候选（最多两种）', exact: true }).count(), 0)
  let detail = await json(qiao, detailPath)
  assert.equal(detail.candidates.length, 2)
  assert.equal(detail.choice, null)
  assert.equal(detail.share, null)
  assert.equal((await get(lin, detailPath)).status(), 404)
  assert.equal((await get(admin, detailPath)).status(), 404)
  assert.equal((await json(lin, `/topics/${topicId}`)).viewpoints.length, 0)
  passed.push('原话与两种私人候选、本人确认及第三人隔离')

  await qiao.page.locator('.candidate-card').filter({ hasText: publishedText }).getByRole('button', { name: '这版准确，我选择它', exact: true }).click()
  await notice(qiao.page, '未增加分享权限')
  detail = await json(qiao, detailPath)
  assert.equal(detail.choice.choice, 'candidate')
  assert.equal(detail.share, null)
  await snapshot(qiao.page, 'desktop-expression-review')
  await qiao.page.getByRole('button', { name: '另一步预览分享', exact: true }).click()
  await qiao.page.getByRole('radio', { name: '日常表达 · 已确认候选 v1', exact: true }).check()
  assert.equal(await qiao.page.locator('.share-preview').innerText(), publishedText)
  await qiao.page.getByLabel(/^分享到哪个议题/).selectOption({ label: topicTitle })
  await qiao.page.getByRole('checkbox').check()
  await snapshot(qiao.page, 'desktop-candidate-share-preview')
  await qiao.page.getByRole('button', { name: '分享预览中的唯一正文', exact: true }).click()
  await notice(qiao.page, '已按预览分享唯一正文')
  const shared = await json(lin, `/topics/${topicId}`)
  assert.equal(shared.viewpoints.length, 1)
  assert.equal(shared.viewpoints[0].text, publishedText)
  for (const privateText of ['SOURCE_ONLY', 'CONTEXT_ONLY', 'TARGET_ONLY', 'PURPOSE_ONLY', 'OTHER_CANDIDATE_ONLY']) assert.equal(JSON.stringify(shared).includes(privateText), false, privateText)
  await topic(lin.page)
  await lin.page.locator('.viewpoint').filter({ hasText: publishedText }).waitFor()
  passed.push('独立分享预览，仅向议题发布所选正文')

  const topicBefore = await json(lin, `/topics/${topicId}`)
  const invitationsBefore = await json(qiao, '/invitations')
  await lin.page.getByRole('button', { name: '我来复述，请作者核对', exact: true }).click()
  await lin.page.getByLabel('我理解的是……', { exact: true }).fill('合成听者复述 LISTENER_ONLY：我以为你会承担清理。请核对。')
  await lin.page.getByRole('button', { name: '把这次复述发给作者核对', exact: true }).click()
  await notice(lin.page, '理解核对已发给表达者')
  const requests = await json(qiao, '/understandings')
  assert.equal(requests.length, 1)
  assert.equal(requests[0].status, 'pending')
  assert.deepEqual(await json(admin, '/understandings'), [])
  assert.deepEqual(await json(lin, `/topics/${topicId}`), topicBefore)
  await nav(qiao.page, '说想法')
  await qiao.page.getByRole('button', { name: '本人核对这次复述', exact: true }).click()
  await qiao.page.getByRole('radio', { name: '部分准确，需要修正', exact: true }).check()
  await qiao.page.getByLabel('修正说明（必填）', { exact: true }).fill('合成作者修正 CORRECTION_ONLY：我只希望核对工具，尚未接受清理劳动。')
  await snapshot(qiao.page, 'desktop-understanding-response')
  await qiao.page.getByRole('button', { name: '保存表达者本人的核对', exact: true }).click()
  await notice(qiao.page, '表达者本人核对已保存')
  assert.equal((await json(lin, '/understandings'))[0].status, 'needs_correction')
  assert.deepEqual(await json(lin, `/topics/${topicId}`), topicBefore)
  assert.deepEqual(await json(qiao, '/invitations'), invitationsBefore)
  await nav(lin.page, '说想法')
  await lin.page.locator('.understanding-card').getByText('合成作者修正 CORRECTION_ONLY：我只希望核对工具，尚未接受清理劳动。', { exact: true }).waitFor()
  passed.push('听者亲自复述、作者私人修正，未改变立场或任务')

  await review(qiao.page, title)
  await qiao.page.locator('.candidate-card').filter({ hasText: publishedText }).getByRole('button', { name: '我来修改', exact: true }).click()
  await qiao.page.getByLabel('候选正文', { exact: true }).fill(`${publishedText} 合成本人补充。`)
  await qiao.page.getByRole('button', { name: '保存候选，稍后本人核对', exact: true }).click()
  await notice(qiao.page, '私人候选已保存')
  detail = await json(qiao, detailPath)
  assert.equal(detail.choice, null)
  assert.equal(detail.share, null)
  assert.equal((await json(lin, `/topics/${topicId}`)).viewpoints.length, 0)
  assert.deepEqual(await json(qiao, '/understandings'), [])
  assert.deepEqual(await json(lin, '/understandings'), [])
  assert.equal(await qiao.page.locator('.understanding-card').count(), 0, 'author mutation clears invalid understanding UI')
  await qiao.page.getByRole('button', { name: '这些转述我不认可', exact: true }).click()
  await notice(qiao.page, '已记录拒绝现有转述')
  assert.equal((await json(qiao, detailPath)).choice.choice, 'no_rephrase')
  await qiao.page.getByRole('button', { name: '只用我的原话', exact: true }).click()
  await notice(qiao.page, '已选择只使用原话')
  assert.equal((await json(qiao, detailPath)).choice.choice, 'original_only')
  await qiao.page.getByRole('dialog').getByRole('button', { name: '编辑原话', exact: true }).click()
  await qiao.page.getByLabel('我的原话', { exact: true }).fill(`${sourceText} 合成新版。`)
  await qiao.page.getByRole('button', { name: '保存私人原话', exact: true }).click()
  await notice(qiao.page, '新版需要本人重新确认')
  detail = await json(qiao, detailPath)
  assert.equal(detail.utterance.version, 2)
  assert.deepEqual(detail.candidates, [])
  assert.equal(detail.choice, null)
  assert.equal(detail.share, null)
  passed.push('修改候选使分享和理解失效；拒绝、只用原话及改源版本')

  await qiao.page.getByRole('button', { name: '本人确认这版准确', exact: true }).click()
  await notice(qiao.page, '尚未因此增加分享权限')
  await qiao.page.getByRole('button', { name: '预览并选择分享', exact: true }).click()
  await qiao.page.getByLabel(/^分享到哪个议题/).selectOption({ label: topicTitle })
  await qiao.page.getByRole('checkbox').check()
  await qiao.page.getByRole('button', { name: '分享预览中的唯一正文', exact: true }).click()
  await notice(qiao.page, '已按预览分享唯一正文')
  assert.equal((await json(lin, `/topics/${topicId}`)).viewpoints[0].representation, 'original')
  await qiao.page.getByRole('button', { name: '撤回分享', exact: true }).click()
  await qiao.page.getByRole('button', { name: '撤回这份表达的分享', exact: true }).click()
  await notice(qiao.page, '分享已撤回')
  assert.equal((await json(lin, `/topics/${topicId}`)).viewpoints.length, 0)
  assert.deepEqual(await json(qiao, '/invitations'), invitationsBefore)
  passed.push('新版原话可另行分享并显式撤回，不改变独立任务回应')

  const mobile = await actor('qiao', 390)
  await nav(mobile.page, '说想法')
  await review(mobile.page, title)
  await snapshot(mobile.page, 'mobile-expression-review')
  await mobile.page.getByRole('button', { name: '手写私人候选（最多两种）', exact: true }).click()
  await snapshot(mobile.page, 'mobile-candidate-editor')
  await mobile.page.getByRole('button', { name: '不保存，返回核对', exact: true }).click()
  await mobile.page.getByRole('button', { name: '关闭窗口', exact: true }).click()
  passed.push('390像素手机原话核对及候选编辑无水平溢出')

  const modelTitle = '合成本地模型协议测试'
  const modelSource = await createSource(qiao.page, modelTitle, '合成测试：我尚未接受任务，请协助改写表达。')
  const modelPath = `/utterances/${modelSource.id}/expression`
  await review(qiao.page, modelTitle)
  await qiao.page.getByRole('button', { name: '检查模型状态', exact: true }).click()
  const aiStatus = await json(qiao, '/ai/status')
  if (fixtureMode) {
    assert.equal(aiStatus.available, true)
    assert.equal(aiStatus.model, 'symsoil-synthetic-test:latest')
    await qiao.page.getByText('本地模型可用', { exact: true }).waitFor()
    await qiao.page.getByLabel('我主动提供的背景语境', { exact: true }).fill('合成且主动提供的背景')
    await qiao.page.getByLabel('希望怎样表达', { exact: true }).fill('合成讨论的平实语言')
    await qiao.page.getByLabel('本次用途', { exact: true }).fill('合成测试，不代表真实模型质量')
    await qiao.page.getByRole('button', { name: '请求最多两个私人建议', exact: true }).click()
    await qiao.page.getByRole('button', { name: '打开编辑，选择是否保存', exact: true }).first().waitFor()
    detail = await json(qiao, modelPath)
    assert.deepEqual(detail.candidates, [])
    assert.equal(detail.choice, null)
    assert.equal(detail.share, null)
    await snapshot(qiao.page, 'desktop-synthetic-model-preview')
    await qiao.page.getByRole('button', { name: '打开编辑，选择是否保存', exact: true }).first().click()
    await qiao.page.getByRole('button', { name: '保存候选，稍后本人核对', exact: true }).click()
    await notice(qiao.page, '私人候选已保存')
    detail = await json(qiao, modelPath)
    assert.equal(detail.candidates[0].origin, 'local_model')
    assert.equal(detail.candidates[0].confirmed_version, null)
    assert.equal(detail.share, null)
    await qiao.page.getByRole('button', { name: '打开编辑，选择是否保存', exact: true }).nth(1).click()
    await qiao.page.getByLabel('候选正文', { exact: true }).fill('合成人工重新写的正文，不伪称模型原始输出。')
    await qiao.page.getByRole('button', { name: '保存候选，稍后本人核对', exact: true }).click()
    await notice(qiao.page, '私人候选已保存')
    detail = await json(qiao, modelPath)
    assert.equal(detail.candidates.find(c => c.kind === 'discussion').origin, 'manual')
    assert.equal(detail.choice, null)
    assert.equal(detail.share, null)
    passed.push('合成HTTP协议通过真实Ollama适配器：预览不保存、完整来源证明、改写记人工')
  } else {
    assert.equal(aiStatus.enabled, false)
    assert.equal(aiStatus.available, false)
    await qiao.page.getByText('本地模型关闭', { exact: true }).waitFor()
    assert.equal(await qiao.page.getByRole('button', { name: '请求最多两个私人建议', exact: true }).isDisabled(), true)
    passed.push('模型默认关闭，人工候选路径仍可完成')
  }
  assert.deepEqual(errors, [], 'browser exceptions')
  assert.deepEqual(external, [], 'external browser resource requests')
  console.log(JSON.stringify({ passed, fixtureMode, realModelInferenceTested: false, browser: browser.version(), errors, external }, null, 2))
} catch (error) {
  if (lastPage) {
    await snapshot(lastPage, 'failure').catch(() => {})
    console.error((await lastPage.locator('body').innerText()).slice(-7000))
  }
  throw error
} finally {
  for (const context of contexts) await context.close()
  await browser.close()
}
