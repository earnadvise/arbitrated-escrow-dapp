import json
import pytest
from genlayer import *


def test_insurance_pool_creation_and_underwriting(direct_deploy, direct_vm):
    """
    Tests creating a parametric risk pool, underwriting liquidity, and premium rate configuration.
    """
    oracle = direct_deploy("contracts/ParametricInsuranceOracle.py")
    underwriter = Address("0x0000000000000000000000000000000000000011")

    direct_vm.sender = underwriter
    direct_vm.value = u256(20000)

    # 500 basis points = 5.0% premium rate
    pool_id = oracle.create_pool("Flight Delay & Disruption Pool", u256(500))
    assert pool_id == u256(0)

    pool = oracle.get_pool(pool_id)
    assert pool.underwriter == underwriter
    assert pool.pool_name == "Flight Delay & Disruption Pool"
    assert pool.total_liquidity == u256(20000)
    assert pool.total_claims_paid == u256(0)
    assert pool.premium_rate_basis_points == u256(500)
    assert pool.active is True


def test_policy_purchase_and_valid_claim_payout(direct_deploy, direct_vm):
    """
    Tests purchasing coverage and successfully claiming indemnity for a verified flight cancellation.
    """
    oracle = direct_deploy("contracts/ParametricInsuranceOracle.py")
    underwriter = Address("0x0000000000000000000000000000000000000011")
    traveler = Address("0x0000000000000000000000000000000000000088")

    # 1. Underwriter funds pool with 50,000 WEI
    direct_vm.sender = underwriter
    direct_vm.value = u256(50000)
    pool_id = oracle.create_pool("Global Aviation Delays", u256(500)) # 5%
    direct_vm.value = u256(0)

    # 2. Traveler buys 1,000 WEI coverage -> 5% premium = 50 WEI
    direct_vm.sender = traveler
    direct_vm.value = u256(50)
    policy_id = oracle.purchase_policy(pool_id, "FLIGHT-BA249-20261010", u256(1000))
    assert policy_id == u256(0)
    direct_vm.value = u256(0)

    policy = oracle.get_policy(policy_id)
    assert policy.status == "ACTIVE"
    assert policy.coverage_amount == u256(1000)
    assert policy.premium_paid == u256(50)

    # 3. Flight is cancelled; traveler files claim with evidence link
    direct_vm.mock_web(
        r".*flightstats.*",
        {"status": 200, "body": "FLIGHT BA249: CANCELLED due to technical malfunction."}
    )
    decision = json.dumps({
        "approved": True,
        "payout_percentage": 100,
        "reasoning": "Official carrier notice confirms flight BA249 cancellation."
    })
    direct_vm.mock_llm(r".*Claims Auditor.*", decision)

    oracle.submit_and_evaluate_claim(policy_id, "https://flightstats.com/tracker/BA249")

    # 4. Verify automated indemnity payout
    settled_policy = oracle.get_policy(policy_id)
    assert settled_policy.status == "CLAIMED_PAID"
    assert settled_policy.claim_payout_amount == u256(1000)
    assert "cancellation" in settled_policy.claim_reasoning.lower()

    pool = oracle.get_pool(pool_id)
    assert pool.total_claims_paid == u256(1000)


def test_fraudulent_or_unverified_claim_rejected(direct_deploy, direct_vm):
    """
    Tests that false or on-time flights have their claims rejected with zero payout.
    """
    oracle = direct_deploy("contracts/ParametricInsuranceOracle.py")
    underwriter = Address("0x0000000000000000000000000000000000000011")
    traveler = Address("0x0000000000000000000000000000000000000088")

    direct_vm.sender = underwriter
    direct_vm.value = u256(20000)
    pool_id = oracle.create_pool("Aviation", u256(1000)) # 10%
    direct_vm.value = u256(0)

    direct_vm.sender = traveler
    direct_vm.value = u256(100)
    policy_id = oracle.purchase_policy(pool_id, "FLIGHT-LH400", u256(1000))
    direct_vm.value = u256(0)

    # Mock on-time flight data
    direct_vm.mock_web(
        r".*radar.*",
        {"status": 200, "body": "FLIGHT LH400: LANDED ON TIME. NO DELAY."}
    )
    decision = json.dumps({
        "approved": False,
        "payout_percentage": 0,
        "reasoning": "Flight arrived on schedule. No disruption detected."
    })
    direct_vm.mock_llm(r".*Claims Auditor.*", decision)

    oracle.submit_and_evaluate_claim(policy_id, "https://radar.com/LH400")

    rejected_policy = oracle.get_policy(policy_id)
    assert rejected_policy.status == "CLAIM_REJECTED"
    assert rejected_policy.claim_payout_amount == u256(0)

    pool = oracle.get_pool(pool_id)
    assert pool.total_claims_paid == u256(0)


def test_pool_top_up_and_underwriter_withdrawal(direct_deploy, direct_vm):
    """
    Tests adding liquidity to an active pool and closing the pool for capital withdrawal.
    """
    oracle = direct_deploy("contracts/ParametricInsuranceOracle.py")
    underwriter = Address("0x0000000000000000000000000000000000000011")
    non_owner = Address("0x0000000000000000000000000000000000000022")

    direct_vm.sender = underwriter
    direct_vm.value = u256(10000)
    pool_id = oracle.create_pool("SLA Uptime Pool", u256(500))

    # Top up liquidity
    direct_vm.value = u256(5000)
    oracle.top_up_liquidity(pool_id)

    pool = oracle.get_pool(pool_id)
    assert pool.total_liquidity == u256(15000)

    # Non-owner cannot close pool
    direct_vm.sender = non_owner
    with pytest.raises(Exception):
        oracle.close_pool(pool_id)

    # Underwriter closes pool
    direct_vm.sender = underwriter
    oracle.close_pool(pool_id)

    closed_pool = oracle.get_pool(pool_id)
    assert closed_pool.active is False
