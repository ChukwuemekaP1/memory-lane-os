"""All model modules in dependency order. Import this (not submodules) so the
mapper registry is fully populated before first use (Alembic env does this)."""

from app.models.ai import AIGeneratedAsset, AIGenerationJob  # noqa: F401
from app.models.archives import Archive, Payment, Subscription, UsageRecord  # noqa: F401
from app.models.audit import AuditEvent  # noqa: F401
from app.models.base import Base  # noqa: F401
from app.models.contributions import (  # noqa: F401
    Contribution,
    ContributionAttachment,
    MediaAsset,
    MediaProcessingJob,
)
from app.models.enums import *  # noqa: F401,F403
from app.models.interactions import (  # noqa: F401
    ContributionTag,
    ModerationRecord,
    Reaction,
    Reply,
)
from app.models.scheduling import Notification, ScheduledEvent  # noqa: F401
from app.models.spaces import (  # noqa: F401
    GuestAccessToken,
    Invitation,
    Space,
    SpaceMembership,
    SpaceSettings,
    Theme,
)
from app.models.users import OtpChallenge, User, UserSession  # noqa: F401
from app.models.uuid7 import uuid7  # noqa: F401
