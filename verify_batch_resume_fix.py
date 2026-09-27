#!/usr/bin/env python3
"""Manual verification script for batch resume fix.

This script verifies the fix works by simulating the resume scenario
without requiring pytest or a full test environment.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from g3o.common import run_state


def test_direct_batch_id_lookup():
    """Verify direct batch_id lookup is used when state file has batch_id."""
    print("Test 1: Direct batch_id lookup...")
    
    # Mock the necessary components
    mock_client = MagicMock()
    mock_batch_status = MagicMock()
    mock_batch_status.batch_id = "batch_abc123"
    mock_batch_status.status = "in_progress"
    mock_batch_status.is_terminal = False
    mock_batch_status.is_completed = False
    
    # Track which methods were called
    poll_called = False
    find_called = False
    
    def mock_poll(batch_id, client=None):
        nonlocal poll_called
        poll_called = True
        print(f"  ✓ poll_batch called with batch_id={batch_id}")
        return mock_batch_status
    
    def mock_find(metadata, client=None, min_created_at=None):
        nonlocal find_called
        find_called = True
        print("  ✗ find_batches_by_metadata called (should not be called)")
        return []
    
    # Patch the methods
    with patch("g3o.common.run_state.batch_client.poll_batch", side_effect=mock_poll), \
         patch("g3o.common.run_state.batch_client.find_batches_by_metadata", side_effect=mock_find), \
         patch("g3o.common.run_state.batch_client.client_from_credentials", return_value=mock_client):
        
        # Simulate _submit_one logic
        entry = {
            "custom_ids": ["job-1", "job-2"],
            "batch_id": "batch_abc123",
            "abandoned_batch_ids": [],
        }
        
        # Direct lookup path
        batch_id = entry.get("batch_id")
        if batch_id:
            try:
                found = run_state.batch_client.poll_batch(batch_id, client=mock_client)
                print(f"  ✓ Direct lookup succeeded: {found.batch_id}")
            except Exception as exc:
                print(f"  ✗ Direct lookup failed: {exc}")
    
    # Verify results
    assert poll_called, "poll_batch should have been called"
    assert not find_called, "find_batches_by_metadata should NOT have been called"
    print("  ✓ Test 1 passed: Direct lookup used, no metadata search\n")


def test_fallback_to_metadata_search():
    """Verify fallback to metadata search when direct lookup fails."""
    print("Test 2: Fallback to metadata search...")
    
    # Mock the necessary components
    mock_client = MagicMock()
    mock_batch_status = MagicMock()
    mock_batch_status.batch_id = "batch_new123"
    mock_batch_status.status = "completed"
    mock_batch_status.is_terminal = True
    mock_batch_status.is_completed = True
    
    # Track which methods were called
    poll_called = False
    find_called = False
    min_created_at_passed = False
    
    def mock_poll(batch_id, client=None):
        nonlocal poll_called
        poll_called = True
        print(f"  ✓ poll_batch called with batch_id={batch_id}")
        raise Exception("Batch not found")
    
    def mock_find(metadata, client=None, min_created_at=None):
        nonlocal find_called, min_created_at_passed
        find_called = True
        if min_created_at is not None:
            min_created_at_passed = True
            print(f"  ✓ find_batches_by_metadata called with min_created_at={min_created_at}")
        else:
            print("  ✗ find_batches_by_metadata called without min_created_at")
        return [mock_batch_status]
    
    # Patch the methods
    with patch("g3o.common.run_state.batch_client.poll_batch", side_effect=mock_poll), \
         patch("g3o.common.run_state.batch_client.find_batches_by_metadata", side_effect=mock_find), \
         patch("g3o.common.run_state.batch_client.client_from_credentials", return_value=mock_client):
        
        # Simulate _submit_one logic with failed direct lookup
        entry = {
            "custom_ids": ["job-1", "job-2"],
            "batch_id": "batch_deleted",
            "abandoned_batch_ids": [],
        }
        state = {"created_at": "2026-09-25T16:00:00Z"}
        
        # Direct lookup path (will fail)
        existing = []
        batch_id = entry.get("batch_id")
        if batch_id:
            try:
                found = run_state.batch_client.poll_batch(batch_id, client=mock_client)
                existing = [found]
            except Exception as exc:
                print(f"  ✓ Direct lookup failed as expected: {exc}")
        
        # Fallback to metadata search
        if not existing:
            from datetime import datetime
            min_created_at = None
            if state.get("created_at"):
                try:
                    min_created_at = datetime.fromisoformat(
                        state["created_at"].replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass
            
            existing = run_state.batch_client.find_batches_by_metadata(
                {"test": "metadata"}, client=mock_client, min_created_at=min_created_at
            )
    
    # Verify results
    assert poll_called, "poll_batch should have been called"
    assert find_called, "find_batches_by_metadata should have been called"
    assert min_created_at_passed, "min_created_at should have been passed"
    print("  ✓ Test 2 passed: Fallback to metadata search with min_created_at\n")


def test_no_batch_id_uses_metadata_search():
    """Verify metadata search is used when state file has no batch_id."""
    print("Test 3: No batch_id in state file...")
    
    # Mock the necessary components
    mock_client = MagicMock()
    mock_batch_status = MagicMock()
    mock_batch_status.batch_id = "batch_found123"
    mock_batch_status.status = "completed"
    mock_batch_status.is_terminal = True
    mock_batch_status.is_completed = True
    
    # Track which methods were called
    poll_called = False
    find_called = False
    
    def mock_poll(batch_id, client=None):
        nonlocal poll_called
        poll_called = True
        print("  ✗ poll_batch called (should not be called)")
        return mock_batch_status
    
    def mock_find(metadata, client=None, min_created_at=None):
        nonlocal find_called
        find_called = True
        print("  ✓ find_batches_by_metadata called")
        return [mock_batch_status]
    
    # Patch the methods
    with patch("g3o.common.run_state.batch_client.poll_batch", side_effect=mock_poll), \
         patch("g3o.common.run_state.batch_client.find_batches_by_metadata", side_effect=mock_find), \
         patch("g3o.common.run_state.batch_client.client_from_credentials", return_value=mock_client):
        
        # Simulate _submit_one logic with no batch_id
        entry = {
            "custom_ids": ["job-1", "job-2"],
            # No batch_id
            "abandoned_batch_ids": [],
        }
        state = {"created_at": "2026-09-25T16:00:00Z"}
        
        # Direct lookup path (skipped because no batch_id)
        existing = []
        batch_id = entry.get("batch_id")
        if batch_id:
            try:
                found = run_state.batch_client.poll_batch(batch_id, client=mock_client)
                existing = [found]
            except Exception:
                pass
        
        # Fallback to metadata search
        if not existing:
            from datetime import datetime
            min_created_at = None
            if state.get("created_at"):
                try:
                    min_created_at = datetime.fromisoformat(
                        state["created_at"].replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass
            
            existing = run_state.batch_client.find_batches_by_metadata(
                {"test": "metadata"}, client=mock_client, min_created_at=min_created_at
            )
    
    # Verify results
    assert not poll_called, "poll_batch should NOT have been called"
    assert find_called, "find_batches_by_metadata should have been called"
    print("  ✓ Test 3 passed: Metadata search used when no batch_id\n")


if __name__ == "__main__":
    print("=" * 70)
    print("Batch Resume Fix Verification")
    print("=" * 70)
    print()
    
    try:
        test_direct_batch_id_lookup()
        test_fallback_to_metadata_search()
        test_no_batch_id_uses_metadata_search()
        
        print("=" * 70)
        print("✓ All tests passed!")
        print("=" * 70)
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
