from sqlalchemy import select

from .models import Invitation, Option, Participant, Stance, Topic, User, Utterance


def user_data(user):
    return {key: getattr(user, key) for key in ("id", "username", "display_name", "role", "active")}


def utterance_data(item):
    return {key: getattr(item, key) for key in ("id", "title", "text", "version", "confirmed_version", "confirmed_at", "shared_topic_id", "created_at", "updated_at")}


def document_data(item):
    return {key: getattr(item, key) for key in ("id", "title", "category", "body", "version", "source", "updated_at")}


def topic_data(db, topic):
    data = {key: getattr(topic, key) for key in ("id", "title", "description", "scope", "status", "version", "owner_id", "created_at")}
    data["participants"] = list(db.scalars(select(Participant.user_id).where(Participant.topic_id == topic.id).order_by(Participant.user_id)))
    data["synthetic"] = True
    return data


def viewpoint_data(db, item):
    author = db.get(User, item.author_id)
    return {"id": item.id, "author_id": item.author_id, "author_name": author.display_name, "text": item.shared_text, "utterance_version": item.shared_version, "confirmed_at": item.confirmed_at}


def invitation_data(db, item):
    data = {key: getattr(item, key) for key in ("id", "topic_id", "invitee_id", "issuer_id", "title", "description", "completion_criteria", "resources", "compensation", "due_date", "status", "version", "note", "created_at")}
    data.update(topic_title=db.get(Topic, item.topic_id).title, invitee_name=db.get(User, item.invitee_id).display_name, synthetic=True)
    return data


def topic_detail(db, topic, actor_id):
    data = topic_data(db, topic)
    data["viewpoints"] = [viewpoint_data(db, item) for item in db.scalars(select(Utterance).where(Utterance.shared_topic_id == topic.id, Utterance.shared_version == Utterance.version, Utterance.confirmed_version == Utterance.version).order_by(Utterance.created_at))]
    options = []
    for item in db.scalars(select(Option).where(Option.topic_id == topic.id).order_by(Option.id)):
        option = {key: getattr(item, key) for key in ("id", "title", "description", "cost", "labor", "risks", "version")}
        option["stances"] = [{"member_id": stance.member_id, "member_name": db.get(User, stance.member_id).display_name, "stance": stance.stance, "condition": stance.condition, "option_version": stance.option_version} for stance in db.scalars(select(Stance).where(Stance.option_id == item.id).order_by(Stance.member_id))]
        options.append(option)
    data["options"] = options
    data["invitations"] = [invitation_data(db, item) for item in db.scalars(select(Invitation).where(Invitation.topic_id == topic.id, (Invitation.issuer_id == actor_id) | (Invitation.invitee_id == actor_id)).order_by(Invitation.created_at))]
    return data
