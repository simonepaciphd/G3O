# T-024 approved LABELS interface

Approved L1-L5/P1-P3, PI 2026-11-01. Generator: PR150 commit 34f6407, unmerged. r11: f948fe0b2a36448db57b70b195567ffc39fb024efb986f9b0025581cee181e0d.

Read support_entailment from generated/jev_questions.json. It carries labels and instructions_page. Each item carries field and values; multipart entries carry parts and repeat the first part as the top-level alias. Select the role part explicitly; never reuse the relationship label for the role. Computed years use value_label=year with empty values. Fixed/computed answer sets require labels; free text does not have a finite value-label map. Select page/activity form from signed label_rules, not a new hard-coded list. One entailment check per supported selected multi-value, keeping signed exemptions and the existing 0.8 bar. Never fill placeholders with raw codes when a label is absent: report the interface defect.

This handoff supplies approved inputs, not independent launch authority. D-007 storage/provenance is approved under RC-D-009 S1a/S2a/P1a/P2; T-012 local writer/instrument is proposed verified at 6cbd551. RC-D-010 applies the existing downgrade rules when classifier probability is unavailable, keeping original code/missing probability and explicit cause. Runtime producer integration remains with T-026/T-028/T-030/T-035; T-050B and external gates remain.
