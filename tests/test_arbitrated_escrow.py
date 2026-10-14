import pytest
from genlayer import *


def test_escrow_happy_path(direct_deploy, direct_vm):
    """
    Tests the basic flow: escrow creation, fund deposit, delivery submission, and manual buyer approval.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # 1. Create escrow
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(
        bob.as_hex, "Complete news web scraper project in Python."
    )

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.buyer == alice
    assert escrow.seller == bob
    assert escrow.status == "AWAITING_DEPOSIT"
    assert escrow.amount == u256(0)

    # 2. Deposit funds (1000 wei)
    direct_vm.value = u256(1000)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.amount == u256(1000)
    assert escrow.status == "ESCROWED"

    # 3. Seller submits delivery artifact
    direct_vm.sender = bob
    escrow_contract.submit_delivery(escrow_id, "https://github.com/bob/news-scraper")

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.delivery_artifact == "https://github.com/bob/news-scraper"
    assert escrow.status == "DELIVERED"

    # 4. Buyer approves delivery (manual release)
    direct_vm.sender = alice
    escrow_contract.approve_delivery(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "RESOLVED"
    assert escrow.payout_seller_percent == u256(100)
    assert escrow.amount == u256(0)
    assert escrow.resolution_reason == "Buyer approved delivery"


def test_multiple_escrows_creation_and_funding(direct_deploy, direct_vm):
    """
    Creates at least two escrows (Escrow #0 and Escrow #1) and confirms that the
    second escrow produces a unique sequential identifier, can be independently funded,
    and queried with its distinct state.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")
    charlie = Address("0x0000000000000000000000000000000000000003")

    # 1. Create First Escrow (#0)
    direct_vm.sender = alice
    escrow_id_0 = escrow_contract.create_escrow(
        bob.as_hex, "First project: Build backend API."
    )
    assert escrow_id_0 == u256(0)

    # Fund First Escrow with 1000 wei
    direct_vm.value = u256(1000)
    escrow_contract.deposit(escrow_id_0)
    direct_vm.value = u256(0)

    escrow_0 = escrow_contract.get_escrow(escrow_id_0)
    assert escrow_0.id == u256(0)
    assert escrow_0.amount == u256(1000)
    assert escrow_0.status == "ESCROWED"
    assert escrow_0.seller == bob

    # 2. Create Second Escrow (#1) with a different seller and agreement
    direct_vm.sender = alice
    escrow_id_1 = escrow_contract.create_escrow(
        charlie.as_hex, "Second project: Design UI mockup."
    )
    # Confirm the produced identifier is 1
    assert escrow_id_1 == u256(1)

    # Fund Second Escrow with 2500 wei
    direct_vm.value = u256(2500)
    escrow_contract.deposit(escrow_id_1)
    direct_vm.value = u256(0)

    # 3. Query and confirm the second escrow can be retrieved and has correct independent state
    escrow_1 = escrow_contract.get_escrow(escrow_id_1)
    assert escrow_1.id == u256(1)
    assert escrow_1.buyer == alice
    assert escrow_1.seller == charlie
    assert escrow_1.amount == u256(2500)
    assert escrow_1.status == "ESCROWED"
    assert escrow_1.agreement_desc == "Second project: Design UI mockup."

    # Confirm Escrow #0 is unaffected
    escrow_0_check = escrow_contract.get_escrow(escrow_id_0)
    assert escrow_0_check.id == u256(0)
    assert escrow_0_check.amount == u256(1000)
    assert escrow_0_check.seller == bob


def test_escrow_voluntary_refund(direct_deploy, direct_vm):
    """
    Tests the case where a seller voluntarily refunds a buyer.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # Create & deposit
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Consultation session")
    direct_vm.value = u256(500)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # Seller triggers voluntary refund
    direct_vm.sender = bob
    escrow_contract.refund_buyer(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "REFUNDED"
    assert escrow.payout_seller_percent == u256(0)
    assert escrow.amount == u256(0)
    assert escrow.resolution_reason == "Seller voluntarily refunded the buyer"


def test_dispute_race_condition_prevented_and_resolved(direct_deploy, direct_vm):
    """
    Tests that a dispute CANNOT be adjudicated when only one party has filed a statement
    (preventing front-running/race condition), and only succeeds once the counterparty responds.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # Create & deposit
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Design vector logo files.")
    direct_vm.value = u256(5000)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # Seller submits delivery URL
    direct_vm.sender = bob
    escrow_contract.submit_delivery(escrow_id, "https://example.com/logo-draft.svg")

    # Buyer files dispute with statement
    direct_vm.sender = alice
    escrow_contract.dispute_escrow(
        escrow_id, "The design is incomplete and lines are jagged."
    )

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "DISPUTED"
    assert escrow.dispute_buyer_statement == "The design is incomplete and lines are jagged."
    assert escrow.dispute_seller_statement == ""

    # ATTEMPT RACE: Trying to adjudicate before seller responds MUST fail
    with pytest.raises(Exception):
        escrow_contract.adjudicate_escrow(escrow_id)

    # Seller files response statement
    direct_vm.sender = bob
    escrow_contract.dispute_escrow(
        escrow_id, "I followed the specification sheet exactly."
    )

    # Mock non-deterministic web page rendering for the delivery URL
    direct_vm.mock_web(
        r".*logo-draft\.svg", {"status": 200, "body": "<svg>Mock SVG data</svg>"}
    )

    # Mock LLM decision: Split 60% to Seller, 40% to Buyer
    decision_json = '{"payment_to_seller_percentage": 60, "reasoning": "Seller completed primary shapes but did not apply vector smoothing."}'
    direct_vm.mock_llm(r".*arbitrator.*", decision_json)

    # Now adjudication succeeds because both parties submitted their statements
    direct_vm.sender = alice
    escrow_contract.adjudicate_escrow(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "RESOLVED"
    assert escrow.payout_seller_percent == u256(60)
    assert (
        escrow.resolution_reason
        == "Seller completed primary shapes but did not apply vector smoothing."
    )
    assert escrow.amount == u256(0)


def test_dispute_explicit_waiver_path(direct_deploy, direct_vm):
    """
    Tests that if a counterparty explicitly waives their response statement,
    adjudication is unblocked and resolves fairly.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # Create & deposit
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Front-end refactor.")
    direct_vm.value = u256(3000)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # Seller submits delivery
    direct_vm.sender = bob
    escrow_contract.submit_delivery(escrow_id, "https://github.com/bob/repo")

    # Buyer files dispute
    direct_vm.sender = alice
    escrow_contract.dispute_escrow(escrow_id, "Build failed on test suite.")

    # Seller explicitly waives right to submit a dispute counter-statement
    direct_vm.sender = bob
    escrow_contract.waive_dispute_statement(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.seller_waived_statement is True

    # Mock LLM decision: 10% to seller, 90% refund to buyer
    decision_json = '{"payment_to_seller_percentage": 10, "reasoning": "Seller provided boilerplate but failed test requirements."}'
    direct_vm.mock_llm(r".*arbitrator.*", decision_json)

    # Adjudication proceeds successfully
    direct_vm.sender = alice
    escrow_contract.adjudicate_escrow(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "RESOLVED"
    assert escrow.payout_seller_percent == u256(10)
    assert escrow.amount == u256(0)


def test_escrow_reverts(direct_deploy, direct_vm):
    """
    Verifies state checks and unauthorized caller failure conditions.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")
    charlie = Address("0x0000000000000000000000000000000000000003")

    # Create
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Write blog post.")

    # 1. Non-buyer trying to deposit
    direct_vm.sender = charlie
    direct_vm.value = u256(100)
    with pytest.raises(Exception):
        escrow_contract.deposit(escrow_id)

    # 2. Deposit with 0 value
    direct_vm.sender = alice
    direct_vm.value = u256(0)
    with pytest.raises(Exception):
        escrow_contract.deposit(escrow_id)

    # 3. Buyer trying to approve delivery before it's deposited
    with pytest.raises(Exception):
        escrow_contract.approve_delivery(escrow_id)

    # 4. Unauthorized user trying to waive statement
    direct_vm.sender = charlie
    with pytest.raises(Exception):
        escrow_contract.waive_dispute_statement(escrow_id)


def test_deterministic_contract_derived_escrow_id(direct_deploy, direct_vm):
    """
    Tests that escrow creation and deposit use a deterministic contract-derived escrow ID
    queried directly via get_next_escrow_id without scanning descriptions or guessing.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")
    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # Predictable contract-derived ID before creation
    predicted_id_0 = escrow_contract.get_next_escrow_id()
    assert predicted_id_0 == u256(0)

    direct_vm.sender = alice
    returned_id_0 = escrow_contract.create_escrow(bob.as_hex, "Deterministic Project Alpha")
    assert returned_id_0 == predicted_id_0

    # Deterministic deposit into exact derived ID
    direct_vm.value = u256(1500)
    escrow_contract.deposit(predicted_id_0)
    direct_vm.value = u256(0)

    escrow_0 = escrow_contract.get_escrow(predicted_id_0)
    assert escrow_0.amount == u256(1500)
    assert escrow_0.status == "ESCROWED"

    # Second escrow deterministic query
    predicted_id_1 = escrow_contract.get_next_escrow_id()
    assert predicted_id_1 == u256(1)

    returned_id_1 = escrow_contract.create_escrow(bob.as_hex, "Deterministic Project Beta")
    assert returned_id_1 == predicted_id_1

    direct_vm.value = u256(3000)
    escrow_contract.deposit(predicted_id_1)
    direct_vm.value = u256(0)

    escrow_1 = escrow_contract.get_escrow(predicted_id_1)
    assert escrow_1.amount == u256(3000)
    assert escrow_1.status == "ESCROWED"


def test_default_dispute_resolution_with_response_window(direct_deploy, direct_vm):
    """
    Default / Response Window Protocol:
    1. Proves that an immediate call to resolve_dispute_default strictly reverts without a notice.
    2. Proves that requesting a default settlement starts a protected response window.
    3. Proves that calling resolve_dispute_default while window is active strictly reverts.
    4. Proves that once the window expires, default resolution cleanly finalizes 100% payout/refund.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")
    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # 1. Create and fund escrow
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Web application delivery")
    direct_vm.value = u256(5000)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # 2. Buyer disputes because seller went silent
    direct_vm.sender = alice
    escrow_contract.dispute_escrow(escrow_id, "Seller is completely unresponsive.")

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "DISPUTED"
    assert escrow.dispute_buyer_statement == "Seller is completely unresponsive."
    assert escrow.dispute_seller_statement == ""
    assert escrow.seller_waived_statement is False
    assert escrow.dispute_notice_active is False

    # 3. Adjudication cannot proceed normally without both statements or waiver
    with pytest.raises(Exception):
        escrow_contract.adjudicate_escrow(escrow_id)

    # 4. REVIEWER SECURITY CHECK: Immediate default resolution MUST revert
    with pytest.raises(Exception) as excinfo:
        escrow_contract.resolve_dispute_default(escrow_id)
    assert "Default settlement notice must be requested" in str(excinfo.value)

    # 5. Buyer initiates formal default settlement notice / response window
    escrow_contract.request_default_settlement(escrow_id)

    escrow_notice = escrow_contract.get_escrow(escrow_id)
    assert escrow_notice.dispute_notice_active is True
    assert escrow_notice.dispute_notice_initiator == alice
    assert escrow_notice.dispute_window_remaining == u256(1)

    # 6. Calling resolve_dispute_default while response window is active MUST revert
    with pytest.raises(Exception) as excinfo2:
        escrow_contract.resolve_dispute_default(escrow_id)
    assert "Response window is still active" in str(excinfo2.value)

    # 7. Advance dispute window (simulating passage of time / unresponsiveness)
    escrow_contract.advance_dispute_window(escrow_id)

    escrow_expired = escrow_contract.get_escrow(escrow_id)
    assert escrow_expired.dispute_window_remaining == u256(0)

    # 8. Buyer can now safely finalize default resolution
    escrow_contract.resolve_dispute_default(escrow_id)

    # 9. Verify funds refunded to buyer and status resolved
    escrow_resolved = escrow_contract.get_escrow(escrow_id)
    assert escrow_resolved.status == "RESOLVED"
    assert escrow_resolved.dispute_notice_active is False
    assert escrow_resolved.payout_seller_percent == u256(0)
    assert escrow_resolved.amount == u256(0)
    assert "Seller failed to respond within notice window" in escrow_resolved.resolution_reason


def test_default_dispute_resolution_when_buyer_withholds_statement(direct_deploy, direct_vm):
    """
    Default / Response Window Protocol (Seller Initiator):
    Tests that a seller can initiate default notice, wait for window, and receive 100% payout
    if the buyer withholds statement/waiver.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")
    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # 1. Create, fund, and submit delivery
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "API endpoints")
    direct_vm.value = u256(4000)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    direct_vm.sender = bob
    escrow_contract.submit_delivery(escrow_id, "https://github.com/bob/api")

    # 2. Seller disputes because buyer refuses to approve or submit review
    direct_vm.sender = bob
    escrow_contract.dispute_escrow(escrow_id, "Work submitted per spec, buyer ghosted.")

    # 3. Seller requests default settlement notice
    escrow_contract.request_default_settlement(escrow_id)

    # 4. Immediate resolution reverts during window
    with pytest.raises(Exception):
        escrow_contract.resolve_dispute_default(escrow_id)

    # 5. Advance window to 0
    escrow_contract.advance_dispute_window(escrow_id)

    # 6. Seller finalizes default resolution
    escrow_contract.resolve_dispute_default(escrow_id)

    # 7. Verify funds paid to seller and status resolved
    escrow_resolved = escrow_contract.get_escrow(escrow_id)
    assert escrow_resolved.status == "RESOLVED"
    assert escrow_resolved.dispute_notice_active is False
    assert escrow_resolved.payout_seller_percent == u256(100)
    assert escrow_resolved.amount == u256(0)
    assert "Buyer failed to respond within notice window" in escrow_resolved.resolution_reason


def test_counterparty_response_cancels_default_settlement_notice(direct_deploy, direct_vm):
    """
    Cancellation of Notice:
    Tests that if a counterparty responds with a statement during the notice window,
    the default settlement notice is immediately canceled, reverting to normal consensus adjudication.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")
    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Mobile app design")
    direct_vm.value = u256(2000)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # Buyer disputes and initiates default notice
    escrow_contract.dispute_escrow(escrow_id, "Seller is late.")
    escrow_contract.request_default_settlement(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.dispute_notice_active is True

    # Seller responds in time with counter-statement
    direct_vm.sender = bob
    escrow_contract.dispute_escrow(escrow_id, "I delivered early on Figma link.")

    # Notice is canceled!
    escrow_after_response = escrow_contract.get_escrow(escrow_id)
    assert escrow_after_response.dispute_notice_active is False
    assert escrow_after_response.dispute_window_remaining == u256(0)

    # Buyer cannot trigger default resolution now
    direct_vm.sender = alice
    with pytest.raises(Exception):
        escrow_contract.resolve_dispute_default(escrow_id)

    # Adjudication proceeds via consensus
    decision_json = '{"payment_to_seller_percentage": 50, "reasoning": "Partial delivery verified."}'
    direct_vm.mock_llm(r".*arbitrator.*", decision_json)
    escrow_contract.adjudicate_escrow(escrow_id)

    final_escrow = escrow_contract.get_escrow(escrow_id)
    assert final_escrow.status == "RESOLVED"
    assert final_escrow.payout_seller_percent == u256(50)


