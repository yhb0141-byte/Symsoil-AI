import argparse
import os
import sys

from sqlalchemy import select

from .db import Base, database_url, make_engine, session_factory
from .models import Document, Invitation, KnowledgeAudience, KnowledgeDocument, KnowledgeReview, KnowledgeRevision, Option, Participant, Topic, User, uid
from .security import password_hasher, stamp


# Only these exact synthetic documents and original account identities can be
# initialized as legacy community publications. No wildcard author assignment.
SYNTHETIC_DOCUMENTS = [
    {"title": "合成示例：如何参加议题", "category": "参与说明", "body": "受邀成员可以表达五类立场。没有回应保持未回应。核对表达准确与同意承担任务是两种操作。", "source": "R0开发团队编写的合成样本；非社区生效制度"},
    {"title": "合成示例：公共场地试办核查表", "category": "协作工具", "body": "先核实负责人、时间边界、噪声条件、清理工具、费用来源和停止条件。本资料不表示场地已经批准使用。", "source": "R0开发团队编写的合成样本；非真实场地许可"},
    {"title": "合成示例：表达与授权", "category": "使用帮助", "body": "私人原话只有作者可见。核对准确不会分享。R0分享时将当前已核对原话主动提交到一个受限议题。撤回或改写后，旧观点不再出现在当前议题里。", "source": "R0产品使用说明合成样本"},
]


def initialize_synthetic_documents(db):
    expected = {"admin": ("合成管理员", "admin"), "lin": ("林禾 · 合成主持人", "facilitator"), "qiao": ("乔雨 · 合成成员", "member")}
    users = {item.username: item for item in db.scalars(select(User).where(User.username.in_(expected)))}
    if len(users) != 3 or any((users[key].display_name, users[key].role) != values for key, values in expected.items()):
        raise ValueError("未发现原始合成 seed 身份；不会为旧资料自动选择作者或审核人")
    owner, reviewer = users["qiao"], users["lin"]
    count = 0
    for item in db.scalars(select(Document).order_by(Document.id)):
        if db.get(KnowledgeDocument, item.id) or item.version != 1:
            continue
        if not any(all(getattr(item, key) == value for key, value in fields.items()) for fields in SYNTHETIC_DOCUMENTS):
            continue
        revision_id, now = uid(), stamp()
        control = KnowledgeDocument(id=item.id, owner_id=owner.id, version=1, latest_revision_id=revision_id, submitted_revision_id=None, reviewer_id=None, published_revision_id=revision_id, access_epoch=1, created_at=now, updated_at=now)
        db.add(control)
        db.flush()
        revision = KnowledgeRevision(id=revision_id, document_id=item.id, number=1, title=item.title, category=item.category, body=item.body, source=item.source, rights="明确的 R0 开发合成样本，仅供开发演示", purpose="开发合成资料目录与引用，不代表社区生效规则", maintainer="R0 开发合成团队", effective_until=None, requested_scope="community", requested_member_ids=[], created_at=now)
        db.add(revision)
        db.flush()
        db.add(KnowledgeAudience(document_id=item.id, revision_id=revision_id, scope="community", member_ids=[]))
        db.add(KnowledgeReview(document_id=item.id, revision_id=revision_id, reviewer_id=reviewer.id, decision="approve", reason="显式初始化原始 seed 合成资料的 legacy community 元数据；不是现实成员审核或社区批准", created_at=now))
        count += 1
    db.flush()
    return count


def seed_demo(db, password: str):
    if len(password) < 12 or len(password) > 128:
        raise ValueError("演示口令须为12至128个字符")
    if db.scalar(select(User.id).limit(1)):
        raise ValueError("数据库已有账号；seed不会覆盖数据或重置口令。请使用独立空演示数据库")
    users = [User(username=username, display_name=name, role=role, password_hash=password_hasher.hash(password), active=True) for username, name, role in (("admin", "合成管理员", "admin"), ("lin", "林禾 · 合成主持人", "facilitator"), ("qiao", "乔雨 · 合成成员", "member"))]
    db.add_all(users)
    db.flush()
    admin, lin, qiao = users
    topic = Topic(title="合成演示：周末公共场地工作坊", description="艺术工作者希望试办一场工作坊，邻居关心安静与清理。本页仅用于开发演示，不代表社区决定。", scope="讨论一次小规模试办的时间、清理分工与停止条件；不批准场地或经费。", owner_id=lin.id, created_at=stamp())
    db.add(topic)
    db.flush()
    db.add_all([Participant(topic_id=topic.id, user_id=user.id) for user in users])
    db.add_all([
        Option(topic_id=topic.id, title="缩小规模，下午试办", description="10位自愿参与者，14:00至16:00，先核查场地负责人同意。", cost="合成估算200元；未承诺支出", labor="清理与带领各需1人自愿接受", risks="噪声、清理遗漏、资源尚未核实"),
        Option(topic_id=topic.id, title="暂缓，先当面沟通", description="邀请邻居和场地负责人先讨论。", cost="未估算", labor="主持人准备沟通材料", risks="进度延后，但保留分歧"),
        Invitation(topic_id=topic.id, invitee_id=qiao.id, issuer_id=lin.id, title="合成邀请：核查工作坊清理条件", description="请考虑是否愿意一起检查场地和工具；你可以拒绝或协商。", completion_criteria="列出清理范围、所需工具与未解决问题", resources="合成工具清单，尚待现场核实", compensation="合成演示中的自愿活动；接受不产生真实履约授权", due_date=None, created_at=stamp()),
    ])
    db.add_all([Document(**fields, updated_at=stamp()) for fields in SYNTHETIC_DOCUMENTS])
    db.flush()
    initialize_synthetic_documents(db)
    db.commit()
    return {user.username: user.id for user in users}


def main():
    parser = argparse.ArgumentParser(description="SymSoil local synthetic-data administration")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed", help="create only synthetic development data in an empty database")
    seed.add_argument("--demo", action="store_true", required=True)
    seed.add_argument("--password", default=None, help="explicit demo-only password (prefer SYMSOIL_DEMO_PASSWORD to avoid shell history)")
    migrate = sub.add_parser("migrate-synthetic-documents", help="explicitly initialize only exact original seed documents; other legacy rows remain quarantined")
    migrate.add_argument("--demo", action="store_true", required=True)
    args = parser.parse_args()
    password = getattr(args, "password", None) or os.getenv("SYMSOIL_DEMO_PASSWORD")
    if args.command == "seed" and not password:
        parser.error("请显式提供--password或SYMSOIL_DEMO_PASSWORD；没有默认口令")
    engine = make_engine(database_url())
    Base.metadata.create_all(engine)
    try:
        with session_factory(engine)() as db:
            if args.command == "seed":
                seed_demo(db, password)
                print("合成R0演示已创建：admin / lin / qiao。未创建任何真实社区决定；口令不会打印。")
            else:
                count = initialize_synthetic_documents(db)
                db.commit()
                print(f"已为 {count} 份精确匹配的原始合成资料建立元数据；未知旧资料仍隔离。")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
