"""PostgreSQL native enums shared by the models (DATABASE_DESIGN)."""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum


class GlobalRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class SpaceVisibility(str, enum.Enum):
    private = "private"
    link = "link"
    scheduled = "scheduled"
    public = "public"


class SpaceKind(str, enum.Enum):
    event = "event"
    ongoing = "ongoing"
    personal = "personal"
    relationship = "relationship"
    family = "family"
    group = "group"
    custom = "custom"


class ContributionPolicy(str, enum.Enum):
    owner_only = "owner_only"
    members = "members"
    link_contributors = "link_contributors"
    anyone_with_link = "anyone_with_link"


class ModerationMode(str, enum.Enum):
    post = "post"
    pre = "pre"


class SpaceRole(str, enum.Enum):
    collaborator = "collaborator"
    contributor = "contributor"
    viewer = "viewer"


class GuestRoleCap(str, enum.Enum):
    viewer = "viewer"
    contributor = "contributor"


class Plan(str, enum.Enum):
    free = "free"
    premium = "premium"


class ContributionKind(str, enum.Enum):
    message = "message"
    story = "story"
    media = "media"
    audio = "audio"
    private_note = "private_note"
    future_letter = "future_letter"


class ContributionStatus(str, enum.Enum):
    pending = "pending"
    visible = "visible"
    hidden = "hidden"
    rejected = "rejected"


class MediaKind(str, enum.Enum):
    image = "image"
    video = "video"
    audio = "audio"
    other = "other"


class MediaStatus(str, enum.Enum):
    reserved = "reserved"
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead = "dead"


class AIJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead = "dead"
    cancelled = "cancelled"


class AIKind(str, enum.Enum):
    transcription = "transcription"
    categorization = "categorization"
    captions = "captions"
    summary = "summary"
    letter = "letter"
    book = "book"
    highlight_film = "highlight_film"
    image_generation = "image_generation"
    story_enhancement = "story_enhancement"


class ReplyStatus(str, enum.Enum):
    visible = "visible"
    hidden = "hidden"


class TagStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    declined = "declined"


class ModerationTarget(str, enum.Enum):
    contribution = "contribution"
    reply = "reply"


class ModerationAction(str, enum.Enum):
    approve = "approve"
    hide = "hide"
    reject = "reject"
    restore = "restore"


class ScheduledKind(str, enum.Enum):
    reveal = "reveal"
    reminder = "reminder"
    future_letter = "future_letter"
    capsule = "capsule"
    digest = "digest"


class ScheduledStatus(str, enum.Enum):
    scheduled = "scheduled"
    claimed = "claimed"
    running = "running"
    done = "done"
    failed = "failed"
    dead = "dead"
    cancelled = "cancelled"


class NotificationKind(str, enum.Enum):
    otp = "otp"
    invite = "invite"
    contribution = "contribution"
    reply = "reply"
    reaction_digest = "reaction_digest"
    reveal = "reveal"
    reminder = "reminder"
    letter = "letter"
    export_ready = "export_ready"
    billing = "billing"
    system = "system"


class NotificationStatus(str, enum.Enum):
    queued = "queued"
    sending = "sending"
    sent = "sent"
    failed = "failed"
    dead = "dead"
    skipped_prefs = "skipped_prefs"


class ArchiveKind(str, enum.Enum):
    full_zip = "full_zip"
    book_pdf = "book_pdf"
    film_mp4 = "film_mp4"
    data_export = "data_export"
    purge = "purge"


class ArchiveStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead = "dead"
    expired = "expired"


class BillingProvider(str, enum.Enum):
    paystack = "paystack"
    stripe = "stripe"
    none = "none"


class MoneyProvider(str, enum.Enum):
    paystack = "paystack"
    stripe = "stripe"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    past_due = "past_due"
    cancelled = "cancelled"
    expired = "expired"


class PaymentKind(str, enum.Enum):
    subscription = "subscription"
    renewal = "renewal"
    one_time = "one_time"
    refund = "refund"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class UsageKind(str, enum.Enum):
    ai_text = "ai_text"
    ai_vision = "ai_vision"
    ai_transcription = "ai_transcription"
    ai_film = "ai_film"
    ai_image = "ai_image"
    storage = "storage"
    export = "export"


# Shared column-type instances for enums used by tables in different modules.
# Reusing one object per PG enum name prevents duplicate CREATE TYPE output.
plan_enum = SAEnum(Plan, name="plan", native_enum=True)
