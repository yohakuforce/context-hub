"""Unit tests for access control domain entities."""

from __future__ import annotations

import pytest
from datetime import datetime

from src.domain.access_control.entities import Consumer, HashedApiKey, Permission
from src.shared.types import ConsumerId, PermissionId, ProjectId, Scope


class TestHashedApiKey:
    def test_creates_with_hash_value(self):
        key = HashedApiKey(hash_value="bcrypt-hash-value")
        assert key.hash_value == "bcrypt-hash-value"
        assert key.algorithm == "bcrypt"

    def test_created_at_auto_set(self):
        key = HashedApiKey(hash_value="hash")
        assert key.created_at is not None
        assert isinstance(key.created_at, datetime)

    def test_explicit_created_at(self):
        dt = datetime(2026, 1, 1)
        key = HashedApiKey(hash_value="hash", created_at=dt)
        assert key.created_at == dt


class TestConsumer:
    @pytest.fixture
    def hashed_key(self):
        return HashedApiKey(hash_value="test-hash")

    def test_create_consumer(self, hashed_key):
        consumer = Consumer.create(name="AI-Project-Manager", hashed_api_key=hashed_key)
        assert consumer.name == "AI-Project-Manager"
        assert consumer.is_active is True
        assert consumer.hashed_api_key == hashed_key

    def test_consumer_has_uuid_id(self, hashed_key):
        consumer = Consumer.create(name="test", hashed_api_key=hashed_key)
        assert len(str(consumer.id)) == 36  # UUID format

    def test_deactivate_returns_new_consumer(self, hashed_key):
        consumer = Consumer.create(name="test", hashed_api_key=hashed_key)
        deactivated = consumer.deactivate()
        assert deactivated.is_active is False
        # Original is unchanged (immutable pattern)
        assert consumer.is_active is True

    def test_deactivated_consumer_preserves_fields(self, hashed_key):
        consumer = Consumer.create(name="AI-Manager", hashed_api_key=hashed_key)
        deactivated = consumer.deactivate()
        assert deactivated.id == consumer.id
        assert deactivated.name == consumer.name
        assert deactivated.hashed_api_key == consumer.hashed_api_key


class TestPermission:
    def test_create_global_permission(self):
        consumer_id = ConsumerId("consumer-001")
        perm = Permission.create(
            consumer_id=consumer_id,
            scopes={Scope.READ, Scope.WRITE},
        )
        assert perm.consumer_id == consumer_id
        assert perm.project_id is None
        assert Scope.READ in perm.scopes
        assert Scope.WRITE in perm.scopes

    def test_create_project_scoped_permission(self):
        consumer_id = ConsumerId("consumer-001")
        project_id = ProjectId("project-abc")
        perm = Permission.create(
            consumer_id=consumer_id,
            scopes={Scope.READ},
            project_id=project_id,
        )
        assert perm.project_id == project_id

    def test_has_scope_direct(self):
        perm = Permission.create(
            consumer_id=ConsumerId("c1"),
            scopes={Scope.READ},
        )
        assert perm.has_scope(Scope.READ) is True
        assert perm.has_scope(Scope.WRITE) is False

    def test_admin_scope_grants_all(self):
        perm = Permission.create(
            consumer_id=ConsumerId("c1"),
            scopes={Scope.ADMIN},
        )
        assert perm.has_scope(Scope.READ) is True
        assert perm.has_scope(Scope.WRITE) is True

    def test_covers_project_global(self):
        perm = Permission.create(
            consumer_id=ConsumerId("c1"),
            scopes={Scope.READ},
            project_id=None,
        )
        assert perm.covers_project(ProjectId("any-project")) is True

    def test_covers_project_specific(self):
        project_id = ProjectId("project-001")
        perm = Permission.create(
            consumer_id=ConsumerId("c1"),
            scopes={Scope.READ},
            project_id=project_id,
        )
        assert perm.covers_project(project_id) is True
        assert perm.covers_project(ProjectId("other-project")) is False
