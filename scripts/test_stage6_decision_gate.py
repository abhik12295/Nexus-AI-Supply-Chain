from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

# The policy gate itself does not call the OpenAI SDK. This stub lets the
# deterministic smoke test run even in a validation environment without openai.
if "openai" not in sys.modules:
    fake_openai = types.ModuleType("openai")

    class _OpenAI:
        pass

    fake_openai.OpenAI = _OpenAI
    sys.modules["openai"] = fake_openai

from services.decision_service import DecisionService


def main() -> None:
    evidence = {
        "searched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_count": 12,
        "sources": [{"source_id": "E1"}],
    }

    caution_review = {
        "verdict": "CAUTION",
        "critical_issue": "Atlanta spare cargo capacity for the proposed diversion volume is unverified.",
        "assessments": [
            {"status": "UNVERIFIED"},
            {"status": "UNVERIFIED"},
            {"status": "SUPPORTED"},
        ],
    }
    caution_gate = DecisionService.evaluate_policy_gate(caution_review, evidence)
    assert caution_gate.must_hold is True
    print("CAUTION + critical issue -> HOLD: PASS")

    pass_review = {
        "verdict": "PASS",
        "critical_issue": None,
        "assessments": [
            {"status": "SUPPORTED"},
            {"status": "SUPPORTED"},
        ],
    }
    pass_gate = DecisionService.evaluate_policy_gate(pass_review, evidence)
    assert pass_gate.must_hold is False
    print("PASS + fresh evidence -> approval may proceed: PASS")

    rejected_review = {
        "verdict": "REJECT",
        "critical_issue": "Alternate hub is directly contradicted by supplied evidence.",
        "assessments": [{"status": "CONTRADICTED"}],
    }
    rejected_gate = DecisionService.evaluate_policy_gate(rejected_review, evidence)
    assert rejected_gate.must_hold is True
    print("REJECT -> HOLD: PASS")


if __name__ == "__main__":
    main()
