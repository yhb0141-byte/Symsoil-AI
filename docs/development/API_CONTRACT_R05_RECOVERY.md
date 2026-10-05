# R0.5 权限收紧日志与恢复水位合同

本合同补充 R0.4、R0.3、R0.2 和 R0 合同。它不新增前端业务按钮，而是约束现有限制性接口的持久化结果。

## 1. 运行配置

| 环境变量 | 默认值 | 约束 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/symsoil.db` | R0.5 只接受本机文件型 SQLite |
| `SYMSOIL_REVOCATION_DIR` | `<数据库路径>.revocations` | 只追加日志目录；不得与可信水位目录相同或互相嵌套 |
| `SYMSOIL_RECOVERY_WITNESS_DIR` | `<数据库路径>.witness` | 可信水位目录；不得与日志目录相同或互相嵌套 |

两个目录都属于运行数据，必须位于持久存储。Compose 将数据库、日志和可信水位分别挂载为三个卷；这只是避免单文件回退静默复活权限，不等于容器恢复演练已经完成。

服务把两个目录权限收紧为 `0700`，把日志、水位和锁文件收紧为 `0600`。运行账户必须独占这些目录；不要通过共享目录向成员分发日志。

## 2. 数据库内部状态

`recovery_state` 只有 `id=singleton` 一行：

- `instance_id`：数据库与外部介质共同持有的随机实例身份；
- `sequence`、`chain_hash`：最后完整确认的权限收紧事件；
- `isolated`、`reason`：是否禁止数据库业务接口及原因。

`recovery_pending` 保存已经在业务库生效、但尚未完成外部确认的最小限制事件。它不保存任何正文。

## 3. 外部事件格式

每行是一个规范 JSON 对象，字段为：

```json
{
  "instance_id": "uuid",
  "sequence": 1,
  "previous_hash": "64位十六进制",
  "event_id": "uuid",
  "action": "utterance.revoke",
  "object_type": "utterance",
  "object_id": "uuid",
  "actor_id": "uuid",
  "object_version": 2,
  "payload": {"shared_topic_id": null},
  "created_at": "UTC时间",
  "hash": "64位十六进制"
}
```

`hash = SHA-256(previous_hash + canonical_json(除 hash 外的完整事件))`。序号必须从 1 连续递增；第一条的 `previous_hash` 是 64 个 `0`。

可信水位只含 `instance_id`、`sequence`、`chain_hash`。服务不接受通过编辑文件人工“对齐”的恢复方式。

## 4. HTTP 可见行为

- 正常成功：沿用原接口状态码和响应体；持久化三方确认完成后才返回。
- 恢复介质异常或存在待确认事件：所有使用数据库依赖的 `/api/v1/*` 接口返回 `503` 和明确的隔离说明，包括登录。
- `/api/v1/health` 仍可返回 `200`，只供进程存活探测。运营者不能以该接口代替业务就绪检查。
- `/api/v1/ready` 不需要登录，但执行完整三方核对；就绪时返回 `200 {"status":"ready"}`，隔离时返回 `503`，且不公开事件数或对象信息。
- 认证、对象访问、版本检查、幂等和原业务合同不变。限制日志不能放宽任何权限。

## 5. 动作映射

| 审计动作 | 最小恢复状态 |
| --- | --- |
| `member.freeze` | `active=false` |
| `utterance.edit`、`utterance.revoke`、`expression.choice` | 当前 `shared_topic_id` |
| `expression.candidate.edit` | 所属原话及当前 `shared_topic_id` |
| `knowledge.cancel_submission`、`knowledge.withdraw`、`knowledge.restrict` | 撤下时间、访问代次、当前送审版本／审核人、受众范围及成员标识 |
| `correction.withdraw` | 当前状态 `withdrawn` |

## 6. 并发与恢复边界

SQLite 业务写入继续由现有进程内写锁串行化，外部日志另以文件锁串行化。此合同不声称多进程或多节点安全。

R0.5 不提供隔离后的写回／重放命令。发生 `503` 后必须停止服务、保全数据库和两个目录的副本，再由后续已验收恢复工具处理。不得删除 `recovery_pending`、修改水位或截断日志来强行启动。
