from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Login(Body):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=1, max_length=128)


class Register(Body):
    token: str = Field(min_length=20, max_length=128)
    password: str = Field(min_length=12, max_length=128)


class AdminInvite(Body):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    role: Literal["admin", "facilitator", "member"]


class UtteranceCreate(Body):
    text: str = Field(min_length=1, max_length=10000)
    title: str = Field(min_length=1, max_length=160)

    @field_validator("text", "title")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("请输入有效文字")
        return value


class Version(Body):
    object_version: int = Field(ge=1)


class UtterancePatch(UtteranceCreate, Version):
    pass


class Share(Version):
    topic_id: str = Field(min_length=1, max_length=36)


class TopicCreate(Body):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    scope: str = Field(min_length=1, max_length=5000)


class ParticipantAdd(Version):
    member_id: str = Field(min_length=1, max_length=36)


class OptionCreate(Version):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    cost: str = Field(max_length=3000)
    labor: str = Field(max_length=3000)
    risks: str = Field(max_length=3000)


class StanceCreate(Body):
    option_id: str = Field(min_length=1, max_length=36)
    option_version: int = Field(ge=1)
    stance: Literal["support", "conditional", "reservation", "oppose", "need_info"]
    condition: str = Field(default="", max_length=5000, validate_default=True)

    @field_validator("condition")
    @classmethod
    def conditional_requires_text(cls, value, info):
        if info.data.get("stance") == "conditional" and not value.strip():
            raise ValueError("附条件支持需要写明条件")
        return value


class InvitationCreate(Body):
    invitee_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    completion_criteria: str = Field(min_length=1, max_length=5000)
    resources: str = Field(max_length=5000)
    compensation: str = Field(max_length=5000)
    due_date: str | None = Field(default=None, max_length=40)

    @field_validator("due_date")
    @classmethod
    def valid_due_date(cls, value):
        if value:
            from datetime import date, datetime
            try:
                date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("截止时间必须为ISO日期或时间") from exc
        return value


class InvitationResponse(Version):
    response: Literal["accepted", "declined", "negotiating"]
    note: str = Field(default="", max_length=5000)
