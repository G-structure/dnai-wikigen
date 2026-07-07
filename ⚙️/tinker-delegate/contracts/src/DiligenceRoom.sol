// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title DiligenceRoom — NDAI escrow for attested ML evaluations
/// @notice Minimal escrow state machine on Base Sepolia. Seller lists artifact,
///         buyer funds evaluation, TEE evaluator submits bounded result,
///         three-way settlement (seller + developer + buyer refund).
contract DiligenceRoom {
    // ── State machine ──────────────────────────────────────────────────
    enum State {
        Created,     // Seller listed, awaiting buyer
        Funded,      // Buyer funded, awaiting TEE evaluation
        Evaluated,   // TEE submitted result, awaiting buyer decision
        Accepted,    // Buyer accepted — seller paid
        Rejected,    // Buyer rejected — seller gets nothing
        Expired      // Deadline passed — refund
    }

    // ── Score bands (bounded output — never raw scores) ────────────────
    enum ScoreBand {
        Negligible,  // <1% improvement
        Low,         // 1-5%
        Medium,      // 5-10%
        High,        // 10-20%
        Exceptional  // >20%
    }

    // ── Deal storage ───────────────────────────────────────────────────
    struct Deal {
        address seller;
        address buyer;
        uint256 reservePrice;      // min payment seller will accept (wei)
        uint256 budgetCap;         // max buyer will pay (wei)
        uint256 expiry;            // unix timestamp
        State state;
        bytes32 artifactHash;      // keccak256 of encrypted artifact
        address teeIdentity;       // TEE-derived address (from KMS key)
        // Evaluation result (set by TEE)
        ScoreBand scoreBand;
        uint256 computeCost;       // Tinker compute cost reported by TEE
        uint256 fee;               // 1% surcharge
        bytes32 resultHash;        // keccak256 of full EvaluationResult
    }

    // ── Constants ──────────────────────────────────────────────────────
    uint256 public constant FEE_BPS = 100;  // 1% = 100 basis points

    // ── State ──────────────────────────────────────────────────────────
    address public immutable developer;
    mapping(uint256 => Deal) public deals;
    mapping(address => uint256) public pendingWithdrawals;
    uint256 public nextDealId;

    // ── Events ─────────────────────────────────────────────────────────
    event DealCreated(
        uint256 indexed dealId,
        address indexed seller,
        uint256 reservePrice,
        uint256 expiry,
        bytes32 artifactHash,
        address teeIdentity
    );
    event DealFunded(
        uint256 indexed dealId,
        address indexed buyer,
        uint256 budgetCap
    );
    event EvaluationSubmitted(
        uint256 indexed dealId,
        ScoreBand scoreBand,
        uint256 computeCost,
        bytes32 resultHash
    );
    event DealAccepted(
        uint256 indexed dealId,
        uint256 sellerPayment,
        uint256 devPayment,
        uint256 buyerRefund
    );
    event DealRejected(
        uint256 indexed dealId,
        uint256 devPayment,
        uint256 buyerRefund
    );
    event DealExpired(uint256 indexed dealId, uint256 refund);
    event PayoutAccrued(uint256 indexed dealId, address indexed recipient, uint256 amount);
    event Withdrawal(address indexed recipient, uint256 amount);

    // ── Errors ─────────────────────────────────────────────────────────
    error InvalidState(State expected, State actual);
    error InvalidExpiry();
    error ZeroArtifactHash();
    error ZeroTEEIdentity();
    error NotSeller();
    error NotBuyer();
    error NotTEE();
    error InsufficientFunding();
    error NotExpired();
    error AlreadyExpired();
    error ComputeCostOverBudget();
    error NothingToWithdraw();
    error PaymentBelowReserve();
    error PaymentAboveBudget();
    error TransferFailed();

    // ── Constructor ────────────────────────────────────────────────────
    constructor() {
        developer = msg.sender;
    }

    // ── Seller creates deal ────────────────────────────────────────────
    /// @notice Seller lists an artifact for evaluation
    /// @param reservePrice Minimum payment the seller will accept (wei)
    /// @param expiry Unix timestamp after which deal can be expired
    /// @param artifactHash keccak256 of the encrypted artifact
    /// @param teeIdentity Address derived from TEE's KMS key
    function createDeal(
        uint256 reservePrice,
        uint256 expiry,
        bytes32 artifactHash,
        address teeIdentity
    ) external returns (uint256 dealId) {
        if (expiry <= block.timestamp) revert InvalidExpiry();
        if (artifactHash == bytes32(0)) revert ZeroArtifactHash();
        if (teeIdentity == address(0)) revert ZeroTEEIdentity();

        dealId = nextDealId++;
        Deal storage d = deals[dealId];
        d.seller = msg.sender;
        d.reservePrice = reservePrice;
        d.expiry = expiry;
        d.artifactHash = artifactHash;
        d.teeIdentity = teeIdentity;
        d.state = State.Created;

        emit DealCreated(dealId, msg.sender, reservePrice, expiry, artifactHash, teeIdentity);
    }

    // ── Buyer funds deal ───────────────────────────────────────────────
    /// @notice Buyer funds the deal. msg.value covers budget_cap.
    ///         Compute cost + fee are deducted from this on settlement.
    function fundDeal(uint256 dealId) external payable {
        Deal storage d = deals[dealId];
        if (d.state != State.Created) revert InvalidState(State.Created, d.state);
        if (block.timestamp >= d.expiry) revert AlreadyExpired();
        if (msg.value == 0) revert InsufficientFunding();

        d.buyer = msg.sender;
        d.budgetCap = msg.value;
        d.state = State.Funded;

        emit DealFunded(dealId, msg.sender, msg.value);
    }

    // ── TEE submits evaluation result ──────────────────────────────────
    /// @notice TEE submits bounded evaluation result + metered compute cost
    /// @param dealId The deal being evaluated
    /// @param scoreBand Bounded score (enum, never raw metrics)
    /// @param computeCost Actual Tinker API cost in wei
    /// @param resultHash keccak256 of the full EvaluationResult struct
    function submitResult(
        uint256 dealId,
        ScoreBand scoreBand,
        uint256 computeCost,
        bytes32 resultHash
    ) external {
        Deal storage d = deals[dealId];
        if (d.state != State.Funded) revert InvalidState(State.Funded, d.state);
        if (msg.sender != d.teeIdentity) revert NotTEE();
        if (block.timestamp >= d.expiry) revert AlreadyExpired();

        uint256 fee = (computeCost * FEE_BPS) / 10000;
        if (computeCost + fee > d.budgetCap) revert ComputeCostOverBudget();

        d.scoreBand = scoreBand;
        d.computeCost = computeCost;
        d.fee = fee;
        d.resultHash = resultHash;
        d.state = State.Evaluated;

        emit EvaluationSubmitted(dealId, scoreBand, computeCost, resultHash);
    }

    // ── Buyer accepts — three-way settlement ───────────────────────────
    /// @notice Buyer accepts the evaluation and sets a deal payment.
    ///         Settlement: seller gets dealPayment, developer gets compute+fee,
    ///         buyer gets remainder.
    /// @param dealId The deal to accept
    /// @param dealPayment Amount to pay the seller (must be >= reservePrice, <= budgetCap)
    function acceptDeal(uint256 dealId, uint256 dealPayment) external {
        Deal storage d = deals[dealId];
        if (d.state != State.Evaluated) revert InvalidState(State.Evaluated, d.state);
        if (msg.sender != d.buyer) revert NotBuyer();
        if (dealPayment < d.reservePrice) revert PaymentBelowReserve();

        uint256 devPayment = d.computeCost + d.fee;
        uint256 totalOut = dealPayment + devPayment;
        if (totalOut > d.budgetCap) revert PaymentAboveBudget();

        d.state = State.Accepted;

        uint256 buyerRefund = d.budgetCap - totalOut;
        _accruePayout(dealId, d.seller, dealPayment);
        _accruePayout(dealId, developer, devPayment);
        _accruePayout(dealId, d.buyer, buyerRefund);

        emit DealAccepted(dealId, dealPayment, devPayment, buyerRefund);
    }

    // ── Buyer rejects — two-way settlement ─────────────────────────────
    /// @notice Buyer rejects. Developer still gets compute+fee (training happened).
    ///         Buyer gets remainder. Seller gets nothing.
    function rejectDeal(uint256 dealId) external {
        Deal storage d = deals[dealId];
        if (d.state != State.Evaluated) revert InvalidState(State.Evaluated, d.state);
        if (msg.sender != d.buyer) revert NotBuyer();

        d.state = State.Rejected;

        uint256 devPayment = d.computeCost + d.fee;
        uint256 buyerRefund = d.budgetCap - devPayment;
        _accruePayout(dealId, developer, devPayment);
        _accruePayout(dealId, d.buyer, buyerRefund);

        emit DealRejected(dealId, devPayment, buyerRefund);
    }

    // ── Expire — anyone can call after deadline ────────────────────────
    /// @notice Expire a deal after its deadline. Refunds buyer (minus any compute).
    function expireDeal(uint256 dealId) external {
        Deal storage d = deals[dealId];
        if (block.timestamp < d.expiry) revert NotExpired();
        if (d.state == State.Accepted || d.state == State.Rejected || d.state == State.Expired) {
            revert InvalidState(State.Funded, d.state);
        }

        State prev = d.state;
        d.state = State.Expired;

        if (prev == State.Created) {
            // No buyer yet — nothing to refund
            emit DealExpired(dealId, 0);
            return;
        }

        // Funded or Evaluated — refund buyer (minus compute if any)
        uint256 devPayment = d.computeCost + d.fee;
        uint256 refund = d.budgetCap - devPayment;
        _accruePayout(dealId, developer, devPayment);
        _accruePayout(dealId, d.buyer, refund);

        emit DealExpired(dealId, refund);
    }

    /// @notice Withdraw claimable proceeds from prior settlements.
    function withdraw() external {
        uint256 amount = pendingWithdrawals[msg.sender];
        if (amount == 0) revert NothingToWithdraw();

        pendingWithdrawals[msg.sender] = 0;

        (bool ok,) = msg.sender.call{value: amount}("");
        if (!ok) {
            pendingWithdrawals[msg.sender] = amount;
            revert TransferFailed();
        }

        emit Withdrawal(msg.sender, amount);
    }

    // ── View helpers ───────────────────────────────────────────────────
    function getDeal(uint256 dealId) external view returns (Deal memory) {
        return deals[dealId];
    }

    function dealCount() external view returns (uint256) {
        return nextDealId;
    }

    function _accruePayout(uint256 dealId, address recipient, uint256 amount) internal {
        if (amount == 0) return;

        pendingWithdrawals[recipient] += amount;
        emit PayoutAccrued(dealId, recipient, amount);
    }
}
