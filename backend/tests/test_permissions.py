"""Capability matrix unit tests (needs_pg; direct predicate checks)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.errors import AppError
from app.models.contributions import Contribution
from app.models.enums import ContributionPolicy, ContributionStatus, GuestRoleCap, SpaceRole
from app.models.spaces import GuestAccessToken
from app.modules.permissions.actor import GuestActor, UserActor
from app.modules.permissions.capabilities import (
    SpaceContext,
    can_delete_item,
    can_edit_item,
    can_edit_space_field,
    can_export,
    can_manage_space,
    can_moderate,
    can_post,
    can_react,
    can_run_ai,
    can_view_item,
    can_view_original,
    display_name,
    load_space_context,
)

pytestmark = pytest.mark.needs_pg


def _member_actor() -> UserActor:
    return UserActor(user_id=uuid4(), email="m@x.com", display_name="M",
                     is_admin=False, session_id=uuid4())


def _owner_actor(user_row) -> UserActor:
    return UserActor(user_id=user_row.id, email=user_row.email,
                     display_name=user_row.display_name, is_admin=False,
                     session_id=uuid4())


def _guest(viewer: bool = False):
    token_id = uuid4()
    cap = GuestRoleCap.viewer if viewer else GuestRoleCap.contributor
    actor = GuestActor(space_id=uuid4(), token_id=token_id, role_cap=cap, label="t")
    token = GuestAccessToken(space_id=actor.space_id, token_hash="h", label="t",
                             role_cap=cap, use_count=0)
    return actor, token


async def _item(session, space, **overrides) -> Contribution:
    params = dict(space_id=space.id, guest_name="Zed", kind="message", body="hi",
                  status=ContributionStatus.visible, is_anonymous=False,
                  is_private_to_owner=False)
    params.update(overrides)
    item = Contribution(**params)
    session.add(item)
    await session.flush()
    return item


async def test_post_policy_matrix(session, space_row, user_row):
    owner = _owner_actor(user_row)
    space_row.owner_id = user_row.id
    member = _member_actor()
    contrib_actor, contrib_token = _guest()
    viewer_actor, viewer_token = _guest(viewer=True)
    contrib_actor = GuestActor(space_id=space_row.id, token_id=contrib_actor.token_id,
                               role_cap=contrib_actor.role_cap, label="t")
    viewer_actor = GuestActor(space_id=space_row.id, token_id=viewer_actor.token_id,
                              role_cap=viewer_actor.role_cap, label="t")

    def ctx_for(policy, actor, role=None, tok=None) -> SpaceContext:
        space_row.contribution_policy = policy
        return SpaceContext(space=space_row, actor=actor, membership_role=role, token=tok)

    assert can_post(ctx_for(ContributionPolicy.owner_only, owner)) is True
    member_ctx = ctx_for(ContributionPolicy.members, member, SpaceRole.contributor)
    assert can_post(member_ctx) is True
    assert can_post(ctx_for(ContributionPolicy.owner_only, member, SpaceRole.contributor)) is False
    assert can_post(ctx_for(ContributionPolicy.link_contributors, contrib_actor, None,
                            contrib_token)) is True
    assert can_post(ctx_for(ContributionPolicy.members, contrib_actor, None,
                            contrib_token)) is False
    assert can_post(ctx_for(ContributionPolicy.anyone_with_link, viewer_actor, None,
                            viewer_token)) is True
    assert can_post(ctx_for(ContributionPolicy.link_contributors, viewer_actor, None,
                            viewer_token)) is False
    assert can_post(ctx_for(ContributionPolicy.anyone_with_link, None)) is False


async def test_item_visibility(session, space_row, user_row):
    owner = _owner_actor(user_row)
    space_row.owner_id = user_row.id
    owner_ctx = SpaceContext(space=space_row, actor=owner)
    stranger_ctx = SpaceContext(space=space_row, actor=None)

    assert can_view_item(owner_ctx, await _item(
        session, space_row, status=ContributionStatus.pending)) is True
    assert can_view_item(stranger_ctx, await _item(
        session, space_row, status=ContributionStatus.pending)) is False
    assert can_view_item(owner_ctx, await _item(
        session, space_row, is_private_to_owner=True)) is True
    assert can_view_item(stranger_ctx, await _item(
        session, space_row, is_private_to_owner=True)) is False

    member = _member_actor()
    mine = await _item(session, space_row, status=ContributionStatus.pending,
                       author_user_id=member.user_id, guest_name=None)
    assert can_view_item(SpaceContext(space=space_row, actor=member), mine) is True


async def test_anonymous_masking(session, space_row, user_row):
    owner = _owner_actor(user_row)
    space_row.owner_id = user_row.id
    item = await _item(session, space_row, is_anonymous=True, guest_name="Zed")
    assert display_name(SpaceContext(space=space_row, actor=owner), item) == "Zed"
    assert display_name(SpaceContext(space=space_row, actor=None), item) is None


async def test_edit_windows(session, space_row, user_row):
    member = _member_actor()
    ctx = SpaceContext(space=space_row, actor=member, membership_role=SpaceRole.contributor)
    fresh = await _item(session, space_row, author_user_id=member.user_id, guest_name=None)
    assert can_edit_item(ctx, fresh) is True
    old = await _item(session, space_row, author_user_id=member.user_id, guest_name=None)
    old.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    await session.flush()
    assert can_edit_item(ctx, old) is False  # member 24h window passed
    assert can_edit_item(ctx, await _item(session, space_row)) is False  # not own


async def test_staff_and_owner_capabilities(session, space_row, user_row):
    owner = _owner_actor(user_row)
    space_row.owner_id = user_row.id
    owner_ctx = SpaceContext(space=space_row, actor=owner)
    collab_ctx = SpaceContext(space=space_row, actor=_member_actor(),
                              membership_role=SpaceRole.collaborator)
    assert can_manage_space(owner_ctx) is True
    assert can_manage_space(collab_ctx) is False
    assert can_moderate(collab_ctx) is True
    assert can_edit_space_field(collab_ctx, "title") is True
    assert can_edit_space_field(collab_ctx, "visibility") is False
    assert can_export(owner_ctx, "film_mp4") is True
    assert can_export(collab_ctx, "film_mp4") is False
    assert can_export(collab_ctx, "full_zip") is True
    assert can_run_ai(collab_ctx) is False  # ai_opt_in False
    space_row.ai_opt_in = True
    assert can_run_ai(collab_ctx) is True


async def test_original_visibility(session, space_row, user_row):
    owner = _owner_actor(user_row)
    space_row.owner_id = user_row.id
    member = _member_actor()
    member_ctx = SpaceContext(space=space_row, actor=member,
                              membership_role=SpaceRole.contributor)
    owner_ctx = SpaceContext(space=space_row, actor=owner)
    stranger_ctx = SpaceContext(space=space_row, actor=None)
    assert can_view_original(owner_ctx, member.user_id, None) is True  # staff
    assert can_view_original(member_ctx, member.user_id, None) is True  # own upload
    assert can_view_original(member_ctx, user_row.id, None) is False
    assert can_view_original(stranger_ctx, member.user_id, None) is False


async def test_admin_bypass_and_limits(session, space_row, user_row):
    space_row.visibility = "private"
    admin = UserActor(user_id=uuid4(), email="a@x.com", display_name="A",
                      is_admin=True, session_id=uuid4())
    ctx = await load_space_context(session, admin, space_row.id)
    assert ctx.via_admin is True
    item = await _item(session, space_row, status=ContributionStatus.pending)
    assert can_view_item(ctx, item) is True
    assert can_delete_item(ctx, item) is True
    assert can_post(ctx) is False  # admins don't post as admins


async def test_guest_space_binding(session, space_row):
    guest = GuestActor(space_id=uuid4(), token_id=uuid4(),
                       role_cap=GuestRoleCap.contributor, label="t")
    with pytest.raises(AppError) as exc:
        await load_space_context(session, guest, space_row.id)
    assert exc.value.code == "not_found"


async def test_deleted_space_owner_only(session, space_row, user_row):
    owner = _owner_actor(user_row)
    space_row.owner_id = user_row.id
    space_row.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    ctx = await load_space_context(session, owner, space_row.id)
    assert ctx.is_owner is True
    with pytest.raises(AppError) as exc:
        await load_space_context(session, None, space_row.id)
    assert exc.value.code == "not_found"


async def test_react_gating(session, space_row):
    viewer_actor, viewer_token = _guest(viewer=True)
    viewer_actor = GuestActor(space_id=space_row.id, token_id=viewer_actor.token_id,
                              role_cap=viewer_actor.role_cap, label="v")
    ctx = SpaceContext(space=space_row, actor=viewer_actor, token=viewer_token)
    assert can_react(ctx) is False
    space_row.allow_viewer_react = True
    assert can_react(ctx) is True
