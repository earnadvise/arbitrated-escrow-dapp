# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import json
from dataclasses import dataclass
import genlayer as gl
from genlayer import *


@allow_storage
@dataclass
class InsurancePool:
    id: u256
    pool_name: str
    underwriter: Address
    total_liquidity: u256
    total_claims_paid: u256
    premium_rate_basis_points: u256  # e.g. 500 = 5.0%
    active: bool


@allow_storage
@dataclass
class Policy:
    id: u256
    pool_id: u256
    policyholder: Address
    event_identifier: str        # e.g. "AA100-2026-10-15" or "AWS-US-EAST-1"
    coverage_amount: u256
    premium_paid: u256
    status: str                  # "ACTIVE" | "CLAIMED_PAID" | "CLAIM_REJECTED" | "EXPIRED"
    claim_evidence_url: str
    claim_payout_amount: u256
    claim_reasoning: str


@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass


class ParametricInsuranceOracle(gl.Contract):
    """
    ParametricInsuranceOracle: A decentralized parametric insurance primitive for Web3.
    Enables autonomous claim assessment and instant indemnity payouts using GenLayer
    AI-validator consensus and live web incident verification (e.g., flight delays, server outages).
    """
    pools: TreeMap[u256, InsurancePool]
    policies: TreeMap[u256, Policy]
    next_pool_id: u256
    next_policy_id: u256

    def __init__(self) -> None:
        self.next_pool_id = u256(0)
        self.next_policy_id = u256(0)

    @gl.public.write.payable
    def create_pool(
        self,
        pool_name: str,
        premium_rate_basis_points: u256
    ) -> u256:
        """
        Creates and funds a new parametric insurance risk pool.
        premium_rate_basis_points: 500 = 5% premium for requested coverage.
        """
        if not pool_name or not pool_name.strip():
            raise gl.vm.UserError("Pool name cannot be empty")

        if premium_rate_basis_points == u256(0) or premium_rate_basis_points > u256(5000):
            raise gl.vm.UserError("Premium rate must be between 1 and 5000 basis points (0.01% - 50%)")

        initial_liquidity = gl.message.value
        if initial_liquidity == u256(0):
            raise gl.vm.UserError("Initial underwriting liquidity must be greater than zero")

        pool_id = self.next_pool_id
        self.next_pool_id = self.next_pool_id + u256(1)

        new_pool = InsurancePool(
            id=pool_id,
            pool_name=pool_name,
            underwriter=gl.message.sender_address,
            total_liquidity=initial_liquidity,
            total_claims_paid=u256(0),
            premium_rate_basis_points=premium_rate_basis_points,
            active=True
        )

        self.pools[pool_id] = new_pool
        return pool_id

    @gl.public.write.payable
    def top_up_liquidity(self, pool_id: u256) -> None:
        """
        Allows underwriters to add additional liquidity to an active pool.
        """
        if pool_id not in self.pools:
            raise gl.vm.UserError("Insurance pool not found")

        pool = self.pools[pool_id]
        if not pool.active:
            raise gl.vm.UserError("Cannot add liquidity to an inactive pool")

        deposit = gl.message.value
        if deposit == u256(0):
            raise gl.vm.UserError("Deposit value must be greater than zero")

        pool.total_liquidity = pool.total_liquidity + deposit
        self.pools[pool_id] = pool

    @gl.public.write.payable
    def purchase_policy(
        self,
        pool_id: u256,
        event_identifier: str,
        requested_coverage: u256
    ) -> u256:
        """
        Purchases a parametric coverage policy.
        The buyer must pay the required premium: (coverage * rate_basis_points) / 10000.
        """
        if pool_id not in self.pools:
            raise gl.vm.UserError("Insurance pool not found")

        pool = self.pools[pool_id]
        if not pool.active:
            raise gl.vm.UserError("Insurance pool is not active")

        if not event_identifier or not event_identifier.strip():
            raise gl.vm.UserError("Event identifier cannot be empty")

        if requested_coverage == u256(0):
            raise gl.vm.UserError("Requested coverage must be greater than zero")

        available_liquidity = pool.total_liquidity - pool.total_claims_paid
        if requested_coverage > available_liquidity:
            raise gl.vm.UserError("Requested coverage exceeds available pool underwriting liquidity")

        # Calculate required premium
        required_premium = (requested_coverage * pool.premium_rate_basis_points) // u256(10000)
        if required_premium == u256(0):
            required_premium = u256(1)

        paid_amount = gl.message.value
        if paid_amount < required_premium:
            raise gl.vm.UserError("Sent premium is below required policy cost")

        # Premiums increase pool liquidity reserves
        pool.total_liquidity = pool.total_liquidity + paid_amount
        self.pools[pool_id] = pool

        policy_id = self.next_policy_id
        self.next_policy_id = self.next_policy_id + u256(1)

        new_policy = Policy(
            id=policy_id,
            pool_id=pool_id,
            policyholder=gl.message.sender_address,
            event_identifier=event_identifier,
            coverage_amount=requested_coverage,
            premium_paid=paid_amount,
            status="ACTIVE",
            claim_evidence_url="",
            claim_payout_amount=u256(0),
            claim_reasoning=""
        )

        self.policies[policy_id] = new_policy
        return policy_id

    @gl.public.write
    def submit_and_evaluate_claim(
        self,
        policy_id: u256,
        evidence_url: str
    ) -> None:
        """
        Policyholder files an insurance claim with a live evidence URL (flight radar, status page, or news advisory).
        Decentralized AI-validators inspect the live incident feed and adjudicate the claim.
        """
        if policy_id not in self.policies:
            raise gl.vm.UserError("Policy not found")

        policy = self.policies[policy_id]
        if policy.policyholder != gl.message.sender_address:
            raise gl.vm.UserError("Only policyholder can submit a claim")

        if policy.status != "ACTIVE":
            raise gl.vm.UserError("Policy is not in active claimable status")

        if not evidence_url or not evidence_url.strip():
            raise gl.vm.UserError("Evidence URL is required")

        pool = self.pools[policy.pool_id]
        if not pool.active:
            raise gl.vm.UserError("Underlying insurance pool is inactive")

        event_id = policy.event_identifier
        coverage = policy.coverage_amount

        # Equivalence Principle Consensus Block
        def verify_claim_nondet() -> str:
            evidence_content = ""
            if evidence_url.startswith("http://") or evidence_url.startswith("https://"):
                try:
                    evidence_content = gl.nondet.web.render(evidence_url, mode="text")
                except Exception as e:
                    evidence_content = f"Error fetching incident evidence: {str(e)}"

            task = f"""
            You are an independent Parametric Insurance Claims Auditor.
            Evaluate this parametric insurance claim:

            POLICY EVENT IDENTIFIER: {event_id}
            COVERAGE REQUESTED: {coverage}
            EVIDENCE URL: {evidence_url}
            LIVE INCIDENT DATA / PAGE CONTENT: {evidence_content[:1500]}

            Rules:
            1. Verify whether the specific incident occurred (e.g. flight cancelled/delayed > 3hrs, service downtime confirmed, or disaster confirmed).
            2. If verified, payout_percentage should be 100 (full indemnity) or a proportional percentage (1 to 100).
            3. If not verified or false claim, approved must be false and payout_percentage must be 0.

            Format strictly as JSON:
            {{
                "approved": bool,
                "payout_percentage": int,
                "reasoning": "Concise summary under 150 characters"
            }}
            """
            res = gl.nondet.exec_prompt(task, response_format="json")
            return json.dumps(res, sort_keys=True)

        result_str = gl.eq_principle.strict_eq(verify_claim_nondet)
        result = json.loads(result_str)

        approved = bool(result.get("approved", False))
        payout_pct = int(result.get("payout_percentage", 0))
        reasoning = str(result.get("reasoning", "Claim processed via AI validator consensus"))

        if approved and payout_pct > 0:
            if payout_pct > 100:
                payout_pct = 100

            payout_amount = (coverage * u256(payout_pct)) // u256(100)
            available = pool.total_liquidity - pool.total_claims_paid
            if payout_amount > available:
                payout_amount = available

            if payout_amount > u256(0):
                _Recipient(policy.policyholder).emit_transfer(value=payout_amount)

            pool.total_claims_paid = pool.total_claims_paid + payout_amount
            policy.status = "CLAIMED_PAID"
            policy.claim_payout_amount = payout_amount
            policy.claim_reasoning = reasoning
            policy.claim_evidence_url = evidence_url
        else:
            policy.status = "CLAIM_REJECTED"
            policy.claim_payout_amount = u256(0)
            policy.claim_reasoning = reasoning
            policy.claim_evidence_url = evidence_url

        self.pools[policy.pool_id] = pool
        self.policies[policy_id] = policy

    @gl.public.write
    def close_pool(self, pool_id: u256) -> None:
        """
        Allows the underwriter to close the pool and withdraw remaining liquidity.
        """
        if pool_id not in self.pools:
            raise gl.vm.UserError("Insurance pool not found")

        pool = self.pools[pool_id]
        if pool.underwriter != gl.message.sender_address:
            raise gl.vm.UserError("Only underwriter can close the insurance pool")

        if not pool.active:
            raise gl.vm.UserError("Pool is already closed")

        remaining = pool.total_liquidity - pool.total_claims_paid
        pool.active = False
        self.pools[pool_id] = pool

        if remaining > u256(0):
            _Recipient(pool.underwriter).emit_transfer(value=remaining)

    @gl.public.view
    def get_pool(self, pool_id: u256) -> InsurancePool:
        if pool_id not in self.pools:
            raise gl.vm.UserError("Insurance pool not found")
        return self.pools[pool_id]

    @gl.public.view
    def get_policy(self, policy_id: u256) -> Policy:
        if policy_id not in self.policies:
            raise gl.vm.UserError("Policy not found")
        return self.policies[policy_id]
