"""Calibration harness: a small labeled corpus + precision/recall metrics.

Detection thresholds (confidence overrides, density floors, auto-fix floor,
similarity cutoffs) used to be hand-tuned with no measurement. This package
turns that into numbers: a labeled set of slop / clean snippets and a scorer
that reports recall on expected detections and false positives on clean files.

Run it with ``python -m bench.run``; ``tests/test_bench.py`` asserts full recall
and zero clean-file false positives as a regression guard.
"""
