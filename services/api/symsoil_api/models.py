from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid():
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_hash: Mapped[str] = mapped_column(Text)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    last_seen_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class RegistrationInvite(Base):
    __tablename__ = "registration_invites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    username: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20))
    issuer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[str] = mapped_column(String(40))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="discussing")
    version: Mapped[int] = mapped_column(Integer, default=1)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(String(40))


class Participant(Base):
    __tablename__ = "participants"
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Utterance(Base):
    __tablename__ = "utterances"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    confirmed_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    shared_topic_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    shared_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shared_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class Option(Base):
    __tablename__ = "options"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    cost: Mapped[str] = mapped_column(Text)
    labor: Mapped[str] = mapped_column(Text)
    risks: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Stance(Base):
    __tablename__ = "stances"
    option_id: Mapped[str] = mapped_column(ForeignKey("options.id"), primary_key=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    stance: Mapped[str] = mapped_column(String(20))
    condition: Mapped[str] = mapped_column(Text)
    option_version: Mapped[int] = mapped_column(Integer)


class Invitation(Base):
    __tablename__ = "task_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id"), index=True)
    invitee_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    issuer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    completion_criteria: Mapped[str] = mapped_column(Text)
    resources: Mapped[str] = mapped_column(Text)
    compensation: Mapped[str] = mapped_column(Text)
    due_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    version: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    body: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(40))


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str] = mapped_column(String(40))
    object_id: Mapped[str] = mapped_column(String(36))
    object_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))


class Idempotency(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor_id", "operation", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    operation: Mapped[str] = mapped_column(String(250))
    key: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))


class ExpressionCandidate(Base):
    __tablename__ = "expression_candidates"
    __table_args__ = (UniqueConstraint("utterance_id", "utterance_version", "kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    utterance_id: Mapped[str] = mapped_column(ForeignKey("utterances.id"), index=True)
    utterance_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text)
    target_context: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    origin: Mapped[str] = mapped_column(String(20), default="manual")
    confirmed_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ExpressionChoice(Base):
    __tablename__ = "expression_choices"
    utterance_id: Mapped[str] = mapped_column(ForeignKey("utterances.id"), primary_key=True)
    utterance_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    choice: Mapped[str] = mapped_column(String(20))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("expression_candidates.id"), nullable=True)
    candidate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ExpressionShare(Base):
    __tablename__ = "expression_shares"
    utterance_id: Mapped[str] = mapped_column(ForeignKey("utterances.id"), primary_key=True)
    utterance_version: Mapped[int] = mapped_column(Integer)
    representation: Mapped[str] = mapped_column(String(20))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("expression_candidates.id"), nullable=True)
    candidate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Understanding(Base):
    __tablename__ = "understanding_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id"), index=True)
    utterance_id: Mapped[str] = mapped_column(ForeignKey("utterances.id"), index=True)
    utterance_version: Mapped[int] = mapped_column(Integer)
    representation: Mapped[str] = mapped_column(String(20))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("expression_candidates.id"), nullable=True)
    candidate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    correction: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Application-maintained references avoid a circular insert dependency with
    # immutable revisions; every endpoint checks document/revision membership.
    latest_revision_id: Mapped[str] = mapped_column(String(36))
    submitted_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    access_epoch: Mapped[int] = mapped_column(Integer, default=0)
    withdrawn_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class KnowledgeRevision(Base):
    __tablename__ = "knowledge_revisions"
    __table_args__ = (UniqueConstraint("document_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    rights: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    maintainer: Mapped[str] = mapped_column(Text)
    effective_until: Mapped[str | None] = mapped_column(String(40), nullable=True)
    requested_scope: Mapped[str] = mapped_column(String(20))
    requested_member_ids: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class KnowledgeAudience(Base):
    __tablename__ = "knowledge_audiences"
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("knowledge_revisions.id"))
    scope: Mapped[str] = mapped_column(String(20))
    # This is an explicit publication-time list, never inferred from roles.
    member_ids: Mapped[list[str]] = mapped_column(JSON)


class KnowledgeReview(Base):
    __tablename__ = "knowledge_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("knowledge_revisions.id"))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
