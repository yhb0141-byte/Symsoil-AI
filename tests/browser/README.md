# R0 真实浏览器流程

此测试启动临时 SQLite 合成库和本机 API，用三个独立浏览器会话操作真实网页，运行完成后删除临时库。请先完成根 README 的依赖安装和前端构建。测试使用本机 8000 端口，不能与另一个服务同时占用。

本轮使用 Playwright 1.51.1 与其 Chromium 134.0.6998.35；它们只属于测试环境，不随应用交付。可在独立临时目录安装该测试版本：

```bash
npm install --prefix /tmp/symsoil-browser-qa playwright@1.51.1
node /tmp/symsoil-browser-qa/node_modules/playwright/cli.js install chromium
read -rs SYMSOIL_DEMO_PASSWORD
export SYMSOIL_DEMO_PASSWORD
SYMSOIL_PLAYWRIGHT_MODULE=/tmp/symsoil-browser-qa/node_modules/playwright/index.mjs \
  .venv/bin/python tests/browser/run.py
unset SYMSOIL_DEMO_PASSWORD
```

使用至少 12 字符的合成测试口令，不使用真实账号密码。如已安装其他 Playwright 环境，可通过 `SYMSOIL_PLAYWRIGHT_MODULE` 指向其模块文件，并记录对应浏览器版本。Linux 缺少浏览器运行库时，按 Playwright 环境要求安装系统依赖。

设置 `SYMSOIL_TEST_ARTIFACTS` 为测试环境的绝对目录可保存截图；截图仅包含合成资料。不要把真实社区截图或数据库提交到公开仓库。

八组流程涵盖资料来源、确认与分享隔离、跨成员观点、编辑失效、方案立场、邀请协商／拒绝／接受、注册与冻结、手机与退出。脚本还拒绝浏览器异常、页面水平溢出及外域资源请求。独立安全测试覆盖的断网退出限制见 `docs/development/VALIDATION.md`。

设置 `SYMSOIL_BROWSER_SCRIPT=tests/browser/security.mjs` 可复跑独立的五组安全界面检查，包括延迟退出竞态、断网退出后显式登录、字段校验和模拟时钟的活跃／闲置处理。该脚本明确断言并记录断网时旧 Cookie 仍能直接访问 API 的 R0 限制，输出 `passed-with-documented-R0-limitation` 不表示这一限制已经修复。

CI 默认运行后端与前端单元检查；此浏览器流程在本轮开发环境单独运行，尚未加入 CI 浏览器矩阵。
