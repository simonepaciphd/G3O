"""Validate layer: cross-source merge, dedup, conservative consolidation.

Push #1 ships only the package skeleton. Implementation in Push #2 will port
the merge/dedup logic from the legacy local pipeline (deduplication anchored
on institution + activity, conservative merge rules, uncertainty flags).
"""
