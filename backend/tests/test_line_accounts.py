"""Tests for automatic LINE-only accounts — Firebase Auth, Firestore and LINE all mocked."""

from types import SimpleNamespace
from unittest.mock import patch

import firebase_admin.auth as firebase_auth
import pytest

from services.line import accounts

LINE_USER_ID = "U" + "b" * 32
UID = "line_" + LINE_USER_ID


@pytest.fixture
def deps():
    with (
        patch.object(accounts, "_init_firebase"),
        patch.object(accounts, "firebase_auth") as auth,
        patch.object(accounts, "quota_service") as quota,
        patch.object(accounts, "client") as client,
        patch.object(accounts, "store") as store,
    ):
        auth.UserNotFoundError = firebase_auth.UserNotFoundError
        auth.UidAlreadyExistsError = firebase_auth.UidAlreadyExistsError
        auth.get_user.side_effect = firebase_auth.UserNotFoundError("no such user")
        client.get_display_name.return_value = "阿明"
        store.create_link_if_absent.return_value = {"uid": UID, "email": ""}
        yield SimpleNamespace(auth=auth, quota=quota, client=client, store=store)


def test_new_user_gets_an_account_named_after_their_line_profile(deps):
    link = accounts.link_new_user(LINE_USER_ID)

    deps.client.get_display_name.assert_called_once_with(LINE_USER_ID)
    deps.auth.create_user.assert_called_once_with(uid=UID, display_name="阿明")
    deps.quota.get_or_create_user.assert_called_once_with(UID, display_name="阿明")
    deps.store.create_link_if_absent.assert_called_once_with(LINE_USER_ID, UID)
    assert link == {"uid": UID, "email": ""}


def test_missing_display_name_creates_the_account_without_one(deps):
    deps.client.get_display_name.return_value = ""

    accounts.link_new_user(LINE_USER_ID)

    deps.auth.create_user.assert_called_once_with(uid=UID, display_name=None)


def test_existing_auth_user_is_reused(deps):
    deps.auth.get_user.side_effect = None  # 先前跑到一半，或刪好友後再加回來

    accounts.link_new_user(LINE_USER_ID)

    deps.auth.create_user.assert_not_called()
    deps.quota.get_or_create_user.assert_called_once_with(UID, display_name="阿明")


def test_concurrent_creation_is_tolerated(deps):
    deps.auth.create_user.side_effect = firebase_auth.UidAlreadyExistsError(
        "exists", cause=None, http_response=None
    )

    link = accounts.link_new_user(LINE_USER_ID)

    deps.quota.get_or_create_user.assert_called_once()
    assert link["uid"] == UID


def test_link_made_meanwhile_wins(deps):
    deps.store.create_link_if_absent.return_value = {"uid": "web-uid", "email": "me@example.com"}
    assert accounts.link_new_user(LINE_USER_ID)["uid"] == "web-uid"
