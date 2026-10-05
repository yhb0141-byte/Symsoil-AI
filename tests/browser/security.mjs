// Independent review; includes an assertion documenting the remaining R0 offline-logout limit.
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.SYMSOIL_PLAYWRIGHT_MODULE || 'playwright');

const browser = await chromium.launch({headless: true, args: ['--no-sandbox']});
const context = await browser.newContext({viewport: {width: 1280, height: 900}});
const base = process.env.SYMSOIL_TEST_URL || 'http://127.0.0.1:8000';
const page = await context.newPage();
const notes = [];
const limitations = [];
async function login(name = 'qiao') {
  await page.getByLabel('用户名', {exact: true}).fill(name);
  await page.getByLabel('密码', {exact: true}).fill(process.env.SYMSOIL_DEMO_PASSWORD);
  await page.getByRole('button', {name: '进入工作台', exact: true}).click();
  await page.getByRole('heading', {name: name === 'qiao' ? '你好，乔雨 · 合成成员。' : '你好，合成管理员。'}).waitFor();
}

try {
  await page.goto(base);
  await login();
  assert.equal(await page.getByRole('button', {name: '发起议题', exact: true}).count(), 0);
  notes.push('普通成员不展示主持人创建入口');
  await page.getByRole('button', {name: /说想法/}).first().click();
  await page.getByRole('button', {name: '写一个私稿', exact: true}).click();
  await page.getByLabel('想法标题', {exact: true}).fill('independent-private-title');
  await page.getByLabel('我的原话', {exact: true}).fill('PRIVATE UNSAVED DRAFT SHOULD DISAPPEAR');
  assert.equal(await page.getByLabel('想法标题', {exact: true}).getAttribute('maxlength'), '160');
  await page.getByRole('button', {name: '保存私人原话', exact: true}).click();
  await page.getByRole('heading', {name: 'independent-private-title', exact: true}).waitFor();
  let releaseLogout;
  const logoutGate = new Promise(resolve => { releaseLogout = resolve; });
  await context.route('**/api/v1/auth/logout', async route => {
    const response = await route.fetch();
    await logoutGate;
    await route.fulfill({response});
  });
  await page.getByRole('button', {name: '退出账号', exact: true}).click();
  await page.getByLabel('用户名', {exact: true}).waitFor();
  assert.equal(await page.locator('button[type="submit"]').isDisabled(), true);
  assert.equal(await page.getByText('PRIVATE UNSAVED DRAFT SHOULD DISAPPEAR').count(), 0);
  releaseLogout();
  await page.getByRole('button', {name: '进入工作台', exact: true}).waitFor();
  assert.equal((await context.request.get(base+'/api/v1/auth/me')).status(), 401);
  await context.unroute('**/api/v1/auth/logout');
  notes.push('注销响应被延迟时立即清私人页面，并阻止新登录直至旧注销响应结束');
  await login();
  await context.route('**/api/v1/auth/logout', route => route.abort('failed'));
  await page.getByRole('button', {name: '退出账号', exact: true}).click();
  await page.getByRole('button', {name: '进入工作台', exact: true}).waitFor();
  assert.equal(await page.locator('textarea').count(), 0);
  assert.equal(await page.getByText('PRIVATE UNSAVED DRAFT SHOULD DISAPPEAR').count(), 0);
  await context.unroute('**/api/v1/auth/logout');
  await page.reload();
  await page.getByRole('button', {name: '进入工作台', exact: true}).waitFor();
  assert.equal(await page.getByRole('heading', {name: '你好，乔雨 · 合成成员。'}).count(), 0);
  const newTab = await context.newPage();
  await newTab.goto(base);
  await newTab.getByRole('button', {name: '进入工作台', exact: true}).waitFor();
  const me = await context.request.get(base + '/api/v1/auth/me');
  assert.equal(me.status(), 200);
  const drafts = await context.request.get(base+'/api/v1/utterances');
  assert.equal(drafts.status(), 200);
  assert.ok((await drafts.json()).some(item => item.title === 'independent-private-title'));
  limitations.push('已实测：网络失败的退出仅清理界面，服务端session及HttpOnly cookie在idle期限内仍可经直接API读取此前私稿，真实公共终端使用前须解决');
  notes.push('退出请求失败后恢复网络/刷新/同浏览器新标签页均要求显式登录，不自动恢复前人页面');
  await newTab.close();
  await login('admin');
  await page.getByRole('button', {name: /我的权限/}).first().click();
  await page.getByRole('button', {name: '进入账号管理', exact: true}).click();
  await page.getByRole('button', {name: '建立加入邀请', exact: true}).click();
  const username = page.getByLabel('用户名', {exact: true});
  assert.equal(await username.getAttribute('maxlength'), '64');
  await username.fill('bad.name');
  assert.equal(await username.evaluate(el => el.checkValidity()), false);
  await username.fill('ok-name');
  assert.equal(await username.evaluate(el => el.checkValidity()), true);
  notes.push('用户名/标题客户端校验与服务端约束一致');
  const activeContext = await browser.newContext({viewport: {width: 1280, height: 900}});
  const activePage = await activeContext.newPage();
  await activePage.clock.install({time: new Date()});
  await activePage.goto(base);
  await activePage.getByLabel('用户名', {exact:true}).fill('qiao');
  await activePage.getByLabel('密码', {exact:true}).fill(process.env.SYMSOIL_DEMO_PASSWORD);
  await activePage.getByRole('button', {name:'进入工作台',exact:true}).click();
  await activePage.getByRole('heading',{name:'你好，乔雨 · 合成成员。'}).waitFor();
  await activePage.getByRole('button',{name:/说想法/}).first().click();
  await activePage.getByRole('button',{name:'写一个私稿',exact:true}).click();
  const input = activePage.getByLabel('我的原话',{exact:true});
  await input.fill('ACTIVE UNSAVED PRIVATE DRAFT');
  for (let i=0;i<8;i++) {
    await input.press('a');
    const heartbeat = activePage.waitForRequest('**/api/v1/auth/me');
    await activePage.clock.runFor(45000);
    await heartbeat;
  }
  assert.ok((await input.inputValue()).startsWith('ACTIVE UNSAVED PRIVATE DRAFT'));
  assert.equal(await activePage.getByRole('button',{name:'进入工作台',exact:true}).count(),0);
  await activePage.clock.runFor(300000);
  await activePage.getByRole('button',{name:'进入工作台',exact:true}).waitFor();
  assert.equal(await activePage.locator('textarea').count(),0);
  assert.equal((await activeContext.request.get(base+'/api/v1/auth/me')).status(),401);
  notes.push('浏览器模拟6分钟持续输入，45s活跃续期请求持续发生且保留私稿；5分钟无交互后清稿并撤销服务端会话');
  await activeContext.close();
  console.log(JSON.stringify({status: 'passed-with-documented-R0-limitation', checks: notes, limitations}, null, 2));
} finally { await browser.close(); }
