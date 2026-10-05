# R0.6 正式决定与行动开始条件 API 合同

所有路径位于 `/api/v1`，所有写入继续要求认证、CSRF、对象权限和版本检查；带星号的操作要求 `Idempotency-Key`。

| 方法与路径 | 操作者 | 作用 |
| --- | --- | --- |
| `POST /admin/approval-authorities`* | 管理员 | 为某成员登记特定议题批准资格 |
| `POST /admin/approval-authorities/{id}/revoke`* | 管理员 | 撤销资格并阻断受影响的待批准决定 |
| `POST /topics/{topic_id}/decisions` | 议题主持人 | 建立绑定方案版本的决定草稿和两类条件 |
| `GET /topics/{topic_id}/decisions` | 议题参与者 | 查看决定状态、规则、条件和批准回执，不含私人表达 |
| `POST /decisions/{id}/submit`* | 议题主持人 | 冻结规则版本、至少两名批准者及必需任务；阻断后重新提交会清除旧批准 |
| `POST /decisions/{id}/conditions/{condition_id}/verify`* | 议题主持人 | 核实一项生效或资源条件 |
| `POST /decisions/{id}/approvals`* | 冻结批准者本人 | 按当前资格批准精确决定版本 |
| `POST /decisions/{id}/start`* | 议题主持人 | 在决定已生效、必需任务已接受、资源条件齐备后开始 |

## 状态与版本

决定状态为 `draft → pending → effective → started`。资格变化把 `pending` 变为 `blocked`；主持人只能用新的 `rule_version` 和当前合格批准者重新提交，决定版本递增，旧批准删除。决定正文和方案版本在本增量不可编辑。

批准记录唯一绑定 `(decision_id, decision_version, approver_id)`，并保存资格 ID 与资格版本。重复相同幂等请求返回同一结果；同键不同负载返回 `409`。

## 生效检查

每次批准或生效条件核实时，服务在事务内检查：

- 状态为 `pending`；
- 决定版本、规则版本和方案版本未变化；
- 全部必需批准者账号有效；
- 每人的议题资格仍有效且版本与批准回执一致；
- 全部 `effect` 条件已核实；
- 每名必需批准者都有该决定版本的本人批准。

只有全部成立才写入 `effective_at`。立场、理解、分享、管理员身份或主持人身份均不能替代批准。

## 开始检查

开始不改变决定已经生效的事实。开始事务另行检查：

- 决定状态为 `effective`；
- 全部冻结的必需任务邀请属于同一议题且状态为 `accepted`；
- 全部 `resource` 条件已核实。

任一缺失返回 `422` 并列出缺失类型，不自动接受任务、不自动核实资源。

## 数据与恢复边界

资格撤销是权限收紧事件，纳入 R0.5 外部日志；事件只保存资格标识、成员／议题标识、版本及被阻断决定标识，不保存决定正文。决定文本仍是合成开发数据。完整决定撤销、恢复重放和生产迁移未交付。
