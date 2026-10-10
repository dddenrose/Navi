"""Tests for scripts/link_line.py --create — Firebase Auth, Firestore and LINE all mocked."""

from types import SimpleNamespace
from unittest.mock import patch

import firebase_admin.auth as firebase_auth
import pytest

from scripts import link_line

LINE_USER_ID = "U" + "b" * 32
UID = "line_" + LINE_USER_ID


@pytest.fixture
def deps():
    with (
        patch.object(link_line, "firebase_auth") as auth,
        patch.object(link_line, "quota_service") as quota,
        patch.object(link_line, "get_link", return_value=None) as get_link,
        patch.object(link_line, "set_link") as set_link,
        patch.object(link_line, "get_display_name", return_value="阿明") as get_name,
    ):
        auth.UserNotFoundError = firebase_auth.UserNotFoundError
        auth.get_user.side_effect = firebase_auth.UserNotFoundError("no such user")
        yield SimpleNamespace(
            auth=auth, quota=quota, get_link=get_link, set_link=set_link, get_name=get_name
        )


def test_create_makes_a_line_only_account_and_links_it(deps):
    link_line.link_new_account(LINE_USER_ID)

    deps.get_name.assert_called_once_with(LINE_USER_ID)
    deps.auth.create_user.assert_called_once_with(uid=UID, display_name="阿明")
    deps.quota.get_or_create_user.assert_called_once_with(UID, display_name="阿明")
    deps.set_link.assert_called_once_with(LINE_USER_ID, UID)


def test_given_display_name_skips_the_profile_lookup(deps):
    link_line.link_new_account(LINE_USER_ID, "Amy")

    deps.get_name.assert_not_called()
    deps.auth.create_user.assert_called_once_with(uid=UID, display_name="Amy")


def test_missing_display_name_creates_the_account_without_one(deps):
    deps.get_name.return_value = ""

    link_line.link_new_account(LINE_USER_ID)

    deps.auth.create_user.assert_called_once_with(uid=UID, display_name=None)
    deps.set_link.assert_called_once_with(LINE_USER_ID, UID)


def test_rerun_reuses_the_existing_account(deps):
    deps.auth.get_user.side_effect = None  # Auth 使用者已存在（上次跑到一半）

    link_line.link_new_account(LINE_USER_ID)

    deps.auth.create_user.assert_not_called()
    deps.quota.get_or_create_user.assert_called_once_with(UID, display_name="阿明")
    deps.set_link.assert_called_once_with(LINE_USER_ID, UID)


def test_already_linked_user_is_left_untouched(deps):
    deps.get_link.return_value = {"uid": "someone-else"}

    link_line.link_new_account(LINE_USER_ID)

    deps.auth.create_user.assert_not_called()
    deps.quota.get_or_create_user.assert_not_called()
    deps.set_link.assert_not_called()
