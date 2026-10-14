# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import json
from dataclasses import dataclass
import genlayer as gl
from genlayer import *


@allow_storage
@dataclass
class EscrowRecord:
    id: u256
    buyer: Address
    seller: Address
    amount: u256
    status: str  # "AWAITING_DEPOSIT" | "ESCROWED" | "DELIVERED" | "DISPUTED" | "RESOLVED" | "REFUNDED"
    agreement_desc: str
    delivery_artifact: str
    dispute_initiator: Address
    dispute_buyer_statement: str
    dispute_seller_statement: str
    buyer_waived_statement: bool
    seller_waived_statement: bool
    dispute_notice_active: bool
    dispute_notice_initiator: Address
    dispute_window_remaining: u256
    resolution_reason: str
    payout_seller_percent: u256


@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass


class ArbitratedEscrow(gl.Contract):
    escrows: TreeMap[u256, EscrowRecord]
    next_escrow_id: u256

    def __init__(self) -> None:
        self.next_escrow_id = u256(0)

    @gl.public.write
    def create_escrow(self, seller_address: str, agreement_desc: str) -> u256:
        """
        Creates a new escrow record.
        """
        escrow_id = self.next_escrow_id
        self.next_escrow_id = self.next_escrow_id + u256(1)

        new_escrow = EscrowRecord(
            id=escrow_id,
            buyer=gl.message.sender_address,
            seller=Address(seller_address),
            amount=u256(0),
            status="AWAITING_DEPOSIT",
            agreement_desc=agreement_desc,
            delivery_artifact="",
            dispute_initiator=Address("0x0000000000000000000000000000000000000000"),
            dispute_buyer_statement="",
            dispute_seller_statement="",
            buyer_waived_statement=False,
            seller_waived_statement=False,
            dispute_notice_active=False,
            dispute_notice_initiator=Address("0x0000000000000000000000000000000000000000"),
            dispute_window_remaining=u256(0),
            resolution_reason="",
            payout_seller_percent=u256(0)
        )
        self.escrows[escrow_id] = new_escrow
        return escrow_id

    @gl.public.write.payable
    def deposit(self, escrow_id: u256) -> None:
        """
        Deposits the contract funds (GEN) into the escrow.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if escrow.buyer != gl.message.sender_address:
            raise gl.vm.UserError("Only the buyer can deposit funds")

        if escrow.status != "AWAITING_DEPOSIT":
            raise gl.vm.UserError("Escrow is not awaiting deposit")

        if gl.message.value == u256(0):
            raise gl.vm.UserError("Deposit value must be greater than 0")

        escrow.amount = gl.message.value
        escrow.status = "ESCROWED"
        self.escrows[escrow_id] = escrow

    @gl.public.write
    def submit_delivery(self, escrow_id: u256, delivery_artifact: str) -> None:
        """
        Allows the seller to submit their delivery (e.g., project URL, IPFS hash, or file contents).
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if escrow.seller != gl.message.sender_address:
            raise gl.vm.UserError("Only the seller can submit delivery")

        if escrow.status != "ESCROWED":
            raise gl.vm.UserError("Escrow is not in active escrowed state")

        escrow.delivery_artifact = delivery_artifact
        escrow.status = "DELIVERED"
        self.escrows[escrow_id] = escrow

    @gl.public.write
    def approve_delivery(self, escrow_id: u256) -> None:
        """
        Allows the buyer to approve the delivery, releasing 100% of the funds to the seller.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if escrow.buyer != gl.message.sender_address:
            raise gl.vm.UserError("Only the buyer can approve delivery")

        if escrow.status not in ["ESCROWED", "DELIVERED"]:
            raise gl.vm.UserError("Escrow cannot be approved in current status")

        amount = escrow.amount
        seller_addr = escrow.seller

        # Transfer funds to the seller
        _Recipient(seller_addr).emit_transfer(value=amount)

        escrow.status = "RESOLVED"
        escrow.payout_seller_percent = u256(100)
        escrow.resolution_reason = "Buyer approved delivery"
        escrow.amount = u256(0)
        self.escrows[escrow_id] = escrow

    @gl.public.write
    def refund_buyer(self, escrow_id: u256) -> None:
        """
        Allows the seller to voluntarily refund the buyer (e.g., if they cannot fulfill the contract).
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if escrow.seller != gl.message.sender_address:
            raise gl.vm.UserError("Only the seller can voluntarily refund the buyer")

        if escrow.status not in ["ESCROWED", "DELIVERED"]:
            raise gl.vm.UserError("Escrow cannot be refunded in current status")

        amount = escrow.amount
        buyer_addr = escrow.buyer

        # Refund the buyer
        _Recipient(buyer_addr).emit_transfer(value=amount)

        escrow.status = "REFUNDED"
        escrow.payout_seller_percent = u256(0)
        escrow.resolution_reason = "Seller voluntarily refunded the buyer"
        escrow.amount = u256(0)
        self.escrows[escrow_id] = escrow

    @gl.public.write
    def dispute_escrow(self, escrow_id: u256, statement: str) -> None:
        """
        Allows either buyer or seller to flag the escrow as disputed and submit their statements.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        if not statement or not statement.strip():
            raise gl.vm.UserError("Dispute statement cannot be empty")

        escrow = self.escrows[escrow_id]
        sender = gl.message.sender_address

        if sender != escrow.buyer and sender != escrow.seller:
            raise gl.vm.UserError("Only the buyer or seller can dispute the escrow")

        if escrow.status not in ["ESCROWED", "DELIVERED", "DISPUTED"]:
            raise gl.vm.UserError("Escrow cannot be disputed in current status")

        if sender == escrow.buyer:
            escrow.dispute_buyer_statement = statement
            escrow.buyer_waived_statement = False
        else:
            escrow.dispute_seller_statement = statement
            escrow.seller_waived_statement = False

        if escrow.status != "DISPUTED":
            escrow.dispute_initiator = sender
            escrow.status = "DISPUTED"

        # If counterparty submits a statement, cancel any pending default resolution notice
        if escrow.dispute_notice_active:
            escrow.dispute_notice_active = False
            escrow.dispute_window_remaining = u256(0)

        self.escrows[escrow_id] = escrow

    @gl.public.write
    def waive_dispute_statement(self, escrow_id: u256) -> None:
        """
        Allows a party to explicitly waive their right to submit a dispute counter-statement,
        unblocking adjudication without requiring them to write a statement.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]
        sender = gl.message.sender_address

        if sender != escrow.buyer and sender != escrow.seller:
            raise gl.vm.UserError("Only the buyer or seller can waive their dispute statement")

        if escrow.status != "DISPUTED":
            raise gl.vm.UserError("Can only waive statement when escrow is in DISPUTED status")

        if sender == escrow.buyer:
            escrow.buyer_waived_statement = True
        else:
            escrow.seller_waived_statement = True

        # If counterparty waives statement, cancel any pending default resolution notice
        if escrow.dispute_notice_active:
            escrow.dispute_notice_active = False
            escrow.dispute_window_remaining = u256(0)

        self.escrows[escrow_id] = escrow

    @gl.public.write
    def request_default_settlement(self, escrow_id: u256) -> None:
        """
        Initiates a formal response window / notice period for default dispute settlement.
        Can only be called by a party who has submitted a statement/waiver when the counterparty
        has not yet responded. The counterparty is given a protected response window.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]
        sender = gl.message.sender_address

        if sender != escrow.buyer and sender != escrow.seller:
            raise gl.vm.UserError("Only buyer or seller can request default settlement")

        if escrow.status != "DISPUTED":
            raise gl.vm.UserError("Escrow must be in DISPUTED status for default settlement notice")

        buyer_participated = bool(escrow.dispute_buyer_statement.strip()) or escrow.buyer_waived_statement
        seller_participated = bool(escrow.dispute_seller_statement.strip()) or escrow.seller_waived_statement

        if buyer_participated and seller_participated:
            raise gl.vm.UserError("Both parties participated; proceed to adjudication")

        if sender == escrow.buyer and not buyer_participated:
            raise gl.vm.UserError("Buyer must submit a statement before requesting default settlement")

        if sender == escrow.seller and not seller_participated:
            raise gl.vm.UserError("Seller must submit a statement before requesting default settlement")

        if escrow.dispute_notice_active:
            raise gl.vm.UserError("Default settlement notice is already active")

        escrow.dispute_notice_active = True
        escrow.dispute_notice_initiator = sender
        # Response window: 1 window round required before finalization
        escrow.dispute_window_remaining = u256(1)
        self.escrows[escrow_id] = escrow

    @gl.public.write
    def advance_dispute_window(self, escrow_id: u256) -> None:
        """
        Advances the response window timer/counter after the counterparty fails to respond.
        Once the window reaches 0, resolve_dispute_default can be safely finalized.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if not escrow.dispute_notice_active:
            raise gl.vm.UserError("No active default settlement notice to advance")

        if escrow.dispute_window_remaining > u256(0):
            escrow.dispute_window_remaining = escrow.dispute_window_remaining - u256(1)

        self.escrows[escrow_id] = escrow

    @gl.public.write
    def resolve_dispute_default(self, escrow_id: u256) -> None:
        """
        Default Resolution Finalization:
        Enforces that default resolution CANNOT be called immediately.
        Requires:
        1. A default settlement notice was initiated (dispute_notice_active == True).
        2. The response window has elapsed (dispute_window_remaining == 0).
        3. The counterparty still failed to submit a statement or waiver during the window.
        4. Called only by the initiator of the notice.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]
        sender = gl.message.sender_address

        if sender != escrow.buyer and sender != escrow.seller:
            raise gl.vm.UserError("Only buyer or seller can trigger default dispute resolution")

        if escrow.status != "DISPUTED":
            raise gl.vm.UserError("Escrow must be in DISPUTED status for default resolution")

        if not escrow.dispute_notice_active:
            raise gl.vm.UserError("Default settlement notice must be requested before default resolution")

        if sender != escrow.dispute_notice_initiator:
            raise gl.vm.UserError("Only the party who requested default settlement notice can finalize it")

        if escrow.dispute_window_remaining > u256(0):
            raise gl.vm.UserError("Response window is still active: counterparty must be given time to respond")

        buyer_participated = bool(escrow.dispute_buyer_statement.strip()) or escrow.buyer_waived_statement
        seller_participated = bool(escrow.dispute_seller_statement.strip()) or escrow.seller_waived_statement

        if buyer_participated and seller_participated:
            raise gl.vm.UserError("Both parties participated; use adjudicate_escrow instead")

        if not buyer_participated and not seller_participated:
            raise gl.vm.UserError("Neither party has submitted a dispute statement")

        total_amount = escrow.amount

        if buyer_participated and not seller_participated:
            if sender != escrow.buyer:
                raise gl.vm.UserError("Only participating buyer can claim default resolution")
            if total_amount > u256(0):
                _Recipient(escrow.buyer).emit_transfer(value=total_amount)
            escrow.status = "RESOLVED"
            escrow.dispute_notice_active = False
            escrow.payout_seller_percent = u256(0)
            escrow.resolution_reason = "Default resolution: Seller failed to respond within notice window"
            escrow.amount = u256(0)

        elif seller_participated and not buyer_participated:
            if sender != escrow.seller:
                raise gl.vm.UserError("Only participating seller can claim default resolution")
            if total_amount > u256(0):
                _Recipient(escrow.seller).emit_transfer(value=total_amount)
            escrow.status = "RESOLVED"
            escrow.dispute_notice_active = False
            escrow.payout_seller_percent = u256(100)
            escrow.resolution_reason = "Default resolution: Buyer failed to respond within notice window"
            escrow.amount = u256(0)

        self.escrows[escrow_id] = escrow

    @gl.public.write
    def adjudicate_escrow(self, escrow_id: u256) -> None:
        """
        Resolves a disputed escrow using the AI-Validator consensus mechanism.
        Enforces that BOTH parties have submitted a statement or explicitly waived their response,
        closing the dispute-response race condition.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if escrow.status != "DISPUTED":
            raise gl.vm.UserError("Escrow is not in disputed state")

        buyer_ready = bool(escrow.dispute_buyer_statement.strip()) or escrow.buyer_waived_statement
        seller_ready = bool(escrow.dispute_seller_statement.strip()) or escrow.seller_waived_statement

        if not buyer_ready or not seller_ready:
            raise gl.vm.UserError(
                "Cannot adjudicate: both parties must submit a dispute statement or explicitly waive their response"
            )

        # Compile inputs for the non-deterministic block
        agreement = escrow.agreement_desc
        artifact = escrow.delivery_artifact
        buyer_stmt = (
            escrow.dispute_buyer_statement
            if escrow.dispute_buyer_statement
            else "[Buyer explicitly waived submitting a counter-statement]"
        )
        seller_stmt = (
            escrow.dispute_seller_statement
            if escrow.dispute_seller_statement
            else "[Seller explicitly waived submitting a counter-statement]"
        )

        def resolve_dispute() -> str:
            # We can attempt to render the artifact if it's a URL
            web_content = ""
            if artifact.startswith("http://") or artifact.startswith("https://"):
                try:
                    web_content = gl.nondet.web.render(artifact, mode="text")
                except Exception as e:
                    web_content = f"Error loading artifact webpage: {str(e)}"

            task = f"""
            You are an independent, neutral decentralized arbitrator. Review the original contract agreement, the seller's submitted delivery artifact (and web content if retrieved), and the statements from both the buyer and seller regarding the dispute.
            
            CONTRACT AGREEMENT:
            {agreement}
            
            DELIVERY ARTIFACT SUBMITTED BY SELLER:
            {artifact}
            
            WEB CONTENT OF ARTIFACT (IF APPLICABLE):
            {web_content}
            
            BUYER STATEMENT:
            {buyer_stmt}
            
            SELLER STATEMENT:
            {seller_stmt}
            
            Determine who is in the right and allocate the percentage of funds (from 0 to 100) to be paid to the Seller, with the remainder refunded to the Buyer.
            Format the output strictly as a JSON object:
            {{
                "payment_to_seller_percentage": int, // Integer from 0 to 100
                "reasoning": str // Detailed reasoning for your decision
            }}
            It is mandatory that you respond only using the JSON format above. Don't include any other words or characters, your output must be only JSON without any formatting prefix or suffix.
            """
            result = gl.nondet.exec_prompt(task, response_format="json")
            return json.dumps(result, sort_keys=True)

        # Call the Equivalence Principle consensus mechanism
        result_str = gl.eq_principle.strict_eq(resolve_dispute)
        result_json = json.loads(result_str)

        payout_percent = int(result_json["payment_to_seller_percentage"])
        reasoning = result_json["reasoning"]

        # Bound check the percentage to protect against LLM hallucinations
        if payout_percent < 0:
            payout_percent = 0
        elif payout_percent > 100:
            payout_percent = 100

        total_amount = escrow.amount
        seller_share = (total_amount * u256(payout_percent)) // u256(100)
        buyer_share = total_amount - seller_share

        # Execute payouts
        if seller_share > u256(0):
            _Recipient(escrow.seller).emit_transfer(value=seller_share)
        if buyer_share > u256(0):
            _Recipient(escrow.buyer).emit_transfer(value=buyer_share)

        # Update state
        escrow.status = "RESOLVED"
        escrow.payout_seller_percent = u256(payout_percent)
        escrow.resolution_reason = reasoning
        escrow.amount = u256(0)
        self.escrows[escrow_id] = escrow

    @gl.public.view
    def get_escrow(self, escrow_id: u256) -> EscrowRecord:
        """
        Returns the details of an escrow record.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")
        return self.escrows[escrow_id]

    @gl.public.view
    def get_next_escrow_id(self) -> u256:
        """
        Returns the next sequential escrow identifier that will be assigned.
        Enables clients to deterministically query and know the exact contract-derived escrow ID.
        """
        return self.next_escrow_id
