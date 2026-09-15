from scripts.release_check import compute_summary_status, compute_verdict


def test_no_go_is_not_masked_by_model_no_evidence():
    results = [{"status": "PASS"}, {"status": "NO-GO"}]

    assert compute_verdict(results, model_no_evidence=True) == "NO-GO"


def test_model_no_evidence_verdict_remains_for_software_pass():
    results = [{"status": "PASS"}, {"status": "PASS"}]

    assert compute_verdict(results, model_no_evidence=True) == "SOFTWARE_GO / MODEL_NO_EVIDENCE"


def test_summary_status_does_not_mask_no_go():
    results = [{"status": "PASS"}, {"status": "NO-GO"}]

    assert compute_summary_status(results) == "NO-GO"


def test_summary_status_keeps_software_go_for_clean_results():
    results = [{"status": "PASS"}, {"status": "PASS"}]

    assert compute_summary_status(results) == "SOFTWARE_GO"


def test_fail_stays_highest_priority():
    results = [{"status": "NO-GO"}, {"status": "FAIL"}]

    assert compute_verdict(results, model_no_evidence=True) == "FAIL"


def test_unknown_status_fails_closed_before_model_no_evidence():
    assert compute_verdict([{"status": "BOGUS"}], model_no_evidence=True) == "FAIL"
    assert compute_verdict([{"status": None}], model_no_evidence=True) == "FAIL"
    assert compute_verdict([], model_no_evidence=True) == "FAIL"

