"""Regression guard tied to the calibration corpus (bench/).

Keeps detection honest: every labeled slop case must still be caught, and no
clean snippet may produce a finding. Tuning a threshold that breaks either of
these fails here.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from bench.corpus import CASES
from bench.harness import evaluate


def test_full_recall_on_slop():
    r = evaluate(CASES)
    assert r["recall"] == 1.0, r["missed"]


def test_no_false_positives_on_clean():
    r = evaluate(CASES)
    assert r["clean_fp"] == 0, r["fp_detail"]
