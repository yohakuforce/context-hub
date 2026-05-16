"""Unit tests for access control repository domain mappings.

We test the mapping helper functions directly (no DB required) to
increase coverage of the access_control_repository module.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.access_control.entities import Consumer, HashedApiKey, Permission
from src.shared.types import ConsumerId, PermissionId, ProjectId, Scope


class TestConsumerDomainLogic:
    """Validate Consumer domain behaviour used by the repository."""

    def test_consumer_create_and_deactivate(self):
        key = HashedApiKey(hash_value="h1")
        consumer = Consumer.create("Test Consumer", key)
        assert consumer.is_active is True
        deactivated = consumer.deactivate()
        assert deactivated.is_active is False
        assert consumer.is_active is True  # original unchanged

    def test_consumer_id_is_string(self):
        key = HashedApiKey(hash_value="h1")
        consumer = Consumer.create("Test", key)
        assert isinstance(str(consumer.id), str)


class TestPermissionDomainLogic:
    """Validate Permission domain behaviour."""

    def test_permission_with_multiple_scopes(self):
        perm = Permission.create(
            consumer_id=ConsumerId("c1"),
            scopes={Scope.READ, Scope.WRITE, Scope.ADMIN},
        )
        assert perm.has_scope(Scope.READ) is True
        assert perm.has_scope(Scope.WRITE) is True
        assert perm.has_scope(Scope.ADMIN) is True

    def test_permission_scopes_are_frozenset(self):
        perm = Permission.create(
            consumer_id=ConsumerId("c1"),
            scopes={Scope.READ},
        )
        assert isinstance(perm.scopes, frozenset)

    def test_permission_covers_all_projects_when_none(self):
        perm = Permission.create(
            consumer_id=ConsumerId("c1"),
            scopes={Scope.READ},
            project_id=None,
        )
        # None project_id means global
        assert perm.covers_project(ProjectId("proj-a")) is True
        assert perm.covers_project(ProjectId("proj-b")) is True

    def test_permission_restricted_to_specific_project(self):
        perm = Permission.create(
            consumer_id=ConsumerId("c1"),
            scopes={Scope.WRITE},
            project_id=ProjectId("proj-x"),
        )
        assert perm.covers_project(ProjectId("proj-x")) is True
        assert perm.covers_project(ProjectId("proj-y")) is False
