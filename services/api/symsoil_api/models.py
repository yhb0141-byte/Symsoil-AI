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
