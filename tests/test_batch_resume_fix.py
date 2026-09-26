"""Tests for batch resume reconciliation fix.

Verifies that _submit_one in run_state.py correctly handles resume scenarios:
1. Direct batch_id lookup (O(1)) when state file has batch_id
2. Fallback to metadata search when direct lookup fails
3. Narrow metadata search window using min_created_at
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from g3o.common import batch_client
from g3o.common.run_state import run_chunked_stage


class TestBatchResumeFix:
    """Test batch resume reconciliation logic."""

    def test_resume_with_existing_batch_id_direct_lookup_succeeds(
        self, tmp_path: Path
    ):
        """When state file has batch_id, direct lookup should be used (O(1))."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        
        # Create state file with existing batch_id
        state_dir = run_dir / "_state"
        state_dir.mkdir()
        state_file = state_dir / "extract.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "stage": "extract",
            "run_id": "test-run",
            "model": "gpt-5-nano",
            "n_jobs": 10,
            "n_chunks": 1,
            "created_at": "2026-09-25T16:00:00Z",
            "chunks": {
                "1": {
                    "custom_ids": ["job-1", "job-2", "job-3"],
                    "n_jobs": 3,
                    "batch_id": "batch_abc123",
                    "submitted_at": "2026-09-25T16:00:10Z",
                    "last_status": "in_progress",
                    "fetched_at": None,
                }
            },
        }))
        
        # Mock batch_client methods
        mock_client = MagicMock()
        mock_batch_status = MagicMock()
        mock_batch_status.batch_id = "batch_abc123"
        mock_batch_status.status = "in_progress"
        mock_batch_status.is_terminal = False
        mock_batch_status.is_completed = False
        
        with patch("g3o.common.run_state.batch_client.poll_batch") as mock_poll, \
             patch("g3o.common.run_state.batch_client.find_batches_by_metadata") as mock_find, \
             patch("g3o.common.run_state.batch_client.client_from_credentials") as mock_creds:
            
            mock_poll.return_value = mock_batch_status
            mock_creds.return_value = mock_client
            
            # Run the stage (should use direct lookup, not metadata search)
            jobs = [MagicMock(custom_id=f"job-{i}") for i in range(1, 4)]
            try:
                run_chunked_stage(
                    run_dir=run_dir,
                    stage="extract",
                    jobs=jobs,
                    run_id="test-run",
                    model="gpt-5-nano",
                    credentials=MagicMock(),
                    max_wait=1,
                    poll_interval=1,
                )
            except Exception:
                pass  # Expected to fail due to incomplete mocks
            
            # Verify direct lookup was called
            mock_poll.assert_called_once_with("batch_abc123", client=mock_client)
            
            # Verify metadata search was NOT called (fast path)
            mock_find.assert_not_called()

    def test_resume_with_existing_batch_id_direct_lookup_fails_fallback_to_metadata(
        self, tmp_path: Path
    ):
        """When direct lookup fails (batch deleted), fallback to metadata search."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        
        # Create state file with existing batch_id
        state_dir = run_dir / "_state"
        state_dir.mkdir()
        state_file = state_dir / "extract.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "stage": "extract",
            "run_id": "test-run",
            "model": "gpt-5-nano",
            "n_jobs": 10,
            "n_chunks": 1,
            "created_at": "2026-09-25T16:00:00Z",
            "chunks": {
                "1": {
                    "custom_ids": ["job-1", "job-2", "job-3"],
                    "n_jobs": 3,
                    "batch_id": "batch_deleted",
                    "submitted_at": "2026-09-25T16:00:10Z",
                    "last_status": "in_progress",
                    "fetched_at": None,
                }
            },
        }))
        
        # Mock batch_client methods
        mock_client = MagicMock()
        mock_batch_status = MagicMock()
        mock_batch_status.batch_id = "batch_new123"
        mock_batch_status.status = "completed"
        mock_batch_status.is_terminal = True
        mock_batch_status.is_completed = True
        
        with patch("g3o.common.run_state.batch_client.poll_batch") as mock_poll, \
             patch("g3o.common.run_state.batch_client.find_batches_by_metadata") as mock_find, \
             patch("g3o.common.run_state.batch_client.client_from_credentials") as mock_creds:
            
            # Direct lookup fails (batch deleted)
            mock_poll.side_effect = Exception("Batch not found")
            
            # Metadata search succeeds
            mock_find.return_value = [mock_batch_status]
            mock_creds.return_value = mock_client
            
            # Run the stage
            jobs = [MagicMock(custom_id=f"job-{i}") for i in range(1, 4)]
            try:
                run_chunked_stage(
                    run_dir=run_dir,
                    stage="extract",
                    jobs=jobs,
                    run_id="test-run",
                    model="gpt-5-nano",
                    credentials=MagicMock(),
                    max_wait=1,
                    poll_interval=1,
                )
            except Exception:
                pass  # Expected to fail due to incomplete mocks
            
            # Verify direct lookup was attempted
            mock_poll.assert_called_once_with("batch_deleted", client=mock_client)
            
            # Verify fallback to metadata search
            mock_find.assert_called_once()
            
            # Verify min_created_at was passed (from state file's created_at)
            call_kwargs = mock_find.call_args[1]
            assert "min_created_at" in call_kwargs
            assert call_kwargs["min_created_at"] is not None

    def test_resume_without_batch_id_uses_metadata_search_with_min_created_at(
        self, tmp_path: Path
    ):
        """When state file has no batch_id, use metadata search with min_created_at."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        
        # Create state file WITHOUT batch_id
        state_dir = run_dir / "_state"
        state_dir.mkdir()
        state_file = state_dir / "extract.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "stage": "extract",
            "run_id": "test-run",
            "model": "gpt-5-nano",
            "n_jobs": 10,
            "n_chunks": 1,
            "created_at": "2026-09-25T16:00:00Z",
            "chunks": {
                "1": {
                    "custom_ids": ["job-1", "job-2", "job-3"],
                    "n_jobs": 3,
                    # No batch_id - chunk was planned but not submitted
                    "submitted_at": None,
                    "last_status": None,
                    "fetched_at": None,
                }
            },
        }))
        
        # Mock batch_client methods
        mock_client = MagicMock()
        mock_batch_status = MagicMock()
        mock_batch_status.batch_id = "batch_found123"
        mock_batch_status.status = "completed"
        mock_batch_status.is_terminal = True
        mock_batch_status.is_completed = True
        
        with patch("g3o.common.run_state.batch_client.poll_batch") as mock_poll, \
             patch("g3o.common.run_state.batch_client.find_batches_by_metadata") as mock_find, \
             patch("g3o.common.run_state.batch_client.client_from_credentials") as mock_creds:
            
            mock_find.return_value = [mock_batch_status]
            mock_creds.return_value = mock_client
            
            # Run the stage
            jobs = [MagicMock(custom_id=f"job-{i}") for i in range(1, 4)]
            try:
                run_chunked_stage(
                    run_dir=run_dir,
                    stage="extract",
                    jobs=jobs,
                    run_id="test-run",
                    model="gpt-5-nano",
                    credentials=MagicMock(),
                    max_wait=1,
                    poll_interval=1,
                )
            except Exception:
                pass  # Expected to fail due to incomplete mocks
            
            # Verify direct lookup was NOT called (no batch_id)
            mock_poll.assert_not_called()
            
            # Verify metadata search was called
            mock_find.assert_called_once()
            
            # Verify min_created_at was passed
            call_kwargs = mock_find.call_args[1]
            assert "min_created_at" in call_kwargs
            assert call_kwargs["min_created_at"] is not None

    def test_resume_with_abandoned_batch_id(self, tmp_path: Path):
        """When batch_id is in abandoned list, skip direct lookup."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        
        # Create state file with abandoned batch_id
        state_dir = run_dir / "_state"
        state_dir.mkdir()
        state_file = state_dir / "extract.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "stage": "extract",
            "run_id": "test-run",
            "model": "gpt-5-nano",
            "n_jobs": 10,
            "n_chunks": 1,
            "created_at": "2026-09-25T16:00:00Z",
            "chunks": {
                "1": {
                    "custom_ids": ["job-1", "job-2", "job-3"],
                    "n_jobs": 3,
                    "batch_id": "batch_abandoned",
                    "submitted_at": "2026-09-25T16:00:10Z",
                    "last_status": "failed",
                    "fetched_at": None,
                    "abandoned_batch_ids": ["batch_abandoned"],
                }
            },
        }))
        
        # Mock batch_client methods
        mock_client = MagicMock()
        mock_batch_status = MagicMock()
        mock_batch_status.batch_id = "batch_new123"
        mock_batch_status.status = "completed"
        mock_batch_status.is_terminal = True
        mock_batch_status.is_completed = True
        
        with patch("g3o.common.run_state.batch_client.poll_batch") as mock_poll, \
             patch("g3o.common.run_state.batch_client.find_batches_by_metadata") as mock_find, \
             patch("g3o.common.run_state.batch_client.client_from_credentials") as mock_creds:
            
            mock_find.return_value = [mock_batch_status]
            mock_creds.return_value = mock_client
            
            # Run the stage
            jobs = [MagicMock(custom_id=f"job-{i}") for i in range(1, 4)]
            try:
                run_chunked_stage(
                    run_dir=run_dir,
                    stage="extract",
                    jobs=jobs,
                    run_id="test-run",
                    model="gpt-5-nano",
                    credentials=MagicMock(),
                    max_wait=1,
                    poll_interval=1,
                )
            except Exception:
                pass  # Expected to fail due to incomplete mocks
            
            # Verify direct lookup was called but result was filtered out
            mock_poll.assert_called_once_with("batch_abandoned", client=mock_client)
            
            # Verify fallback to metadata search (because batch was abandoned)
            mock_find.assert_called_once()

    def test_resume_with_terminal_failed_batch_raises_error(self, tmp_path: Path):
        """When batch is in terminal failed state, raise error (no auto-resubmit)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        
        # Create state file with failed batch
        state_dir = run_dir / "_state"
        state_dir.mkdir()
        state_file = state_dir / "extract.json"
        state_file.write_text(json.dumps({
            "schema_version": 2,
            "stage": "extract",
            "run_id": "test-run",
            "model": "gpt-5-nano",
            "n_jobs": 10,
            "n_chunks": 1,
            "created_at": "2026-09-25T16:00:00Z",
            "chunks": {
                "1": {
                    "custom_ids": ["job-1", "job-2", "job-3"],
                    "n_jobs": 3,
                    "batch_id": "batch_failed",
                    "submitted_at": "2026-09-25T16:00:10Z",
                    "last_status": "failed",
                    "fetched_at": None,
                }
            },
        }))
        
        # Mock batch_client methods
        mock_client = MagicMock()
        mock_batch_status = MagicMock()
        mock_batch_status.batch_id = "batch_failed"
        mock_batch_status.status = "failed"
        mock_batch_status.is_terminal = True
        mock_batch_status.is_completed = False  # Terminal but not completed
        
        with patch("g3o.common.run_state.batch_client.poll_batch") as mock_poll, \
             patch("g3o.common.run_state.batch_client.client_from_credentials") as mock_creds:
            
            mock_poll.return_value = mock_batch_status
            mock_creds.return_value = mock_client
            
            # Run the stage - should raise RuntimeError
            jobs = [MagicMock(custom_id=f"job-{i}") for i in range(1, 4)]
            with pytest.raises(RuntimeError, match="orphaned batch"):
                run_chunked_stage(
                    run_dir=run_dir,
                    stage="extract",
                    jobs=jobs,
                    run_id="test-run",
                    model="gpt-5-nano",
                    credentials=MagicMock(),
                    max_wait=1,
                    poll_interval=1,
                )
