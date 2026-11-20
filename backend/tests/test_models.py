"""ORM-level constraint/relationship tests (needs_pg; mirrors the SQL probes)."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.contributions import Contribution
from app.models.spaces import GuestAccessToken, SpaceMembership
from app.models.users import User

pytestmark = pytest.mark.needs_pg


async def test_duplicate_email_rejected_case_insensitive(session, user_row):
    session.add(User(email="OWNER@example.com", display_name="Dup", role_global="user",
                     locale="en", timezone="Africa/Lagos", marketing_opt_in=False))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_membership_unique_per_space(session, space_row, user_row):
    from app.models.users import User as UserModel

    other = UserModel(email="other@example.com", display_name="O", role_global="user",
                      locale="en", timezone="Africa/Lagos", marketing_opt_in=False)
    session.add(other)
    await session.flush()
    session.add(SpaceMembership(space_id=space_row.id, user_id=user_row.id, role="viewer"))
    session.add(SpaceMembership(space_id=space_row.id, user_id=other.id, role="viewer"))
    await session.flush()
    session.add(SpaceMembership(space_id=space_row.id, user_id=other.id, role="viewer"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_contribution_requires_attribution(session, space_row):
    session.add(Contribution(space_id=space_row.id, kind="message", status="visible",
                             is_anonymous=False, is_private_to_owner=False))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_private_future_letter_rejected(session, space_row):
    from datetime import datetime, timezone

    session.add(Contribution(space_id=space_row.id, guest_name="Zed", kind="future_letter",
                             status="visible", is_anonymous=False, is_private_to_owner=True,
                             taken_at=datetime.now(timezone.utc)))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_space_delete_cascades_children(session, space_row, user_row):
    from app.models.enums import GuestRoleCap

    session.add(SpaceMembership(space_id=space_row.id, user_id=user_row.id, role="viewer"))
    session.add(GuestAccessToken(space_id=space_row.id, token_hash="h", label="L",
                                 role_cap=GuestRoleCap.viewer, use_count=0))
    session.add(Contribution(space_id=space_row.id, guest_name="Zed", kind="message",
                             status="visible", is_anonymous=False, is_private_to_owner=False))
    await session.flush()
    await session.delete(space_row)
    await session.flush()
    for model in (SpaceMembership, GuestAccessToken, Contribution):
        count = await session.scalar(select(func.count()).select_from(model))
        assert count == 0


async def test_user_delete_restricted_by_subscription(session, user_row):
    from app.models.archives import Subscription

    session.add(Subscription(user_id=user_row.id, plan="premium", provider="paystack",
                             status="active", cancel_at_period_end=False))
    await session.flush()
    await session.delete(user_row)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_uuid7_primary_keys_assigned(session):
    user = User(email="fresh@example.com", display_name="F", role_global="user",
                locale="en", timezone="Africa/Lagos", marketing_opt_in=False)
    session.add(user)
    await session.flush()
    assert isinstance(user.id, uuid.UUID)
    assert user.id.version == 7
