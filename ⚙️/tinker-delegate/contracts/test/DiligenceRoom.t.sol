// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {DiligenceRoom} from "../src/DiligenceRoom.sol";

contract RevertingReceiver {
    DiligenceRoom internal immutable room;

    constructor(DiligenceRoom _room) {
        room = _room;
    }

    function createDeal(
        uint256 reservePrice,
        uint256 expiry,
        bytes32 artifactHash,
        address teeIdentity
    ) external returns (uint256) {
        return room.createDeal(reservePrice, expiry, artifactHash, teeIdentity);
    }

    function withdraw() external {
        room.withdraw();
    }

    receive() external payable {
        revert("nope");
    }
}

contract DiligenceRoomTest is Test {
    DiligenceRoom public room;

    address dev = address(this);
    address seller = makeAddr("seller");
    address buyer = makeAddr("buyer");
    address tee = makeAddr("tee");

    uint256 reservePrice = 0.5 ether;
    uint256 budgetCap = 2 ether;
    uint256 expiry;
    bytes32 artifactHash = keccak256("test-artifact");

    function setUp() public {
        room = new DiligenceRoom();
        expiry = block.timestamp + 1 days;
        vm.deal(buyer, 10 ether);
    }

    // ── Helpers ────────────────────────────────────────────────────────

    function _createDeal() internal returns (uint256) {
        vm.prank(seller);
        return room.createDeal(reservePrice, expiry, artifactHash, tee);
    }

    function _fundDeal(uint256 dealId) internal {
        vm.prank(buyer);
        room.fundDeal{value: budgetCap}(dealId);
    }

    function _submitResult(
        uint256 dealId,
        DiligenceRoom.ScoreBand band,
        uint256 computeCost
    ) internal {
        vm.prank(tee);
        room.submitResult(dealId, band, computeCost, keccak256("result"));
    }

    // ── Creation ───────────────────────────────────────────────────────

    function test_CreateDeal() public {
        uint256 id = _createDeal();
        assertEq(id, 0);

        DiligenceRoom.Deal memory d = room.getDeal(id);
        assertEq(d.seller, seller);
        assertEq(d.reservePrice, reservePrice);
        assertEq(d.expiry, expiry);
        assertEq(d.artifactHash, artifactHash);
        assertEq(d.teeIdentity, tee);
        assertEq(uint8(d.state), uint8(DiligenceRoom.State.Created));
    }

    function test_CreateDeal_RevertInvalidExpiry() public {
        vm.prank(seller);
        vm.expectRevert(DiligenceRoom.InvalidExpiry.selector);
        room.createDeal(reservePrice, block.timestamp, artifactHash, tee);
    }

    function test_CreateDeal_RevertZeroArtifactHash() public {
        vm.prank(seller);
        vm.expectRevert(DiligenceRoom.ZeroArtifactHash.selector);
        room.createDeal(reservePrice, expiry, bytes32(0), tee);
    }

    function test_CreateDeal_RevertZeroTEEIdentity() public {
        vm.prank(seller);
        vm.expectRevert(DiligenceRoom.ZeroTEEIdentity.selector);
        room.createDeal(reservePrice, expiry, artifactHash, address(0));
    }

    function test_DealCountIncrements() public {
        _createDeal();
        _createDeal();
        assertEq(room.dealCount(), 2);
    }

    // ── Funding ────────────────────────────────────────────────────────

    function test_FundDeal() public {
        uint256 id = _createDeal();
        _fundDeal(id);

        DiligenceRoom.Deal memory d = room.getDeal(id);
        assertEq(d.buyer, buyer);
        assertEq(d.budgetCap, budgetCap);
        assertEq(uint8(d.state), uint8(DiligenceRoom.State.Funded));
    }

    function test_FundDeal_RevertWrongState() public {
        uint256 id = _createDeal();
        _fundDeal(id);

        // Try to fund again
        vm.prank(buyer);
        vm.expectRevert();
        room.fundDeal{value: 1 ether}(id);
    }

    function test_FundDeal_RevertExpired() public {
        uint256 id = _createDeal();
        vm.warp(expiry + 1);

        vm.prank(buyer);
        vm.expectRevert(DiligenceRoom.AlreadyExpired.selector);
        room.fundDeal{value: budgetCap}(id);
    }

    function test_FundDeal_RevertZeroValue() public {
        uint256 id = _createDeal();

        vm.prank(buyer);
        vm.expectRevert(DiligenceRoom.InsufficientFunding.selector);
        room.fundDeal{value: 0}(id);
    }

    // ── Evaluation ─────────────────────────────────────────────────────

    function test_SubmitResult() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.High, 0.1 ether);

        DiligenceRoom.Deal memory d = room.getDeal(id);
        assertEq(uint8(d.state), uint8(DiligenceRoom.State.Evaluated));
        assertEq(uint8(d.scoreBand), uint8(DiligenceRoom.ScoreBand.High));
        assertEq(d.computeCost, 0.1 ether);
        assertEq(d.fee, 0.001 ether); // 1% of 0.1
    }

    function test_SubmitResult_RevertNotTEE() public {
        uint256 id = _createDeal();
        _fundDeal(id);

        vm.prank(seller);
        vm.expectRevert(DiligenceRoom.NotTEE.selector);
        room.submitResult(id, DiligenceRoom.ScoreBand.High, 0.1 ether, keccak256("r"));
    }

    function test_SubmitResult_RevertWrongState() public {
        uint256 id = _createDeal();
        // Not funded yet
        vm.prank(tee);
        vm.expectRevert();
        room.submitResult(id, DiligenceRoom.ScoreBand.High, 0.1 ether, keccak256("r"));
    }

    function test_SubmitResult_RevertComputeCostOverBudget() public {
        uint256 id = _createDeal();
        _fundDeal(id);

        vm.prank(tee);
        vm.expectRevert(DiligenceRoom.ComputeCostOverBudget.selector);
        room.submitResult(id, DiligenceRoom.ScoreBand.High, 1.99 ether, keccak256("r"));
    }

    // ── Accept ─────────────────────────────────────────────────────────

    function test_AcceptDeal() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.High, 0.1 ether);

        uint256 sellerBefore = seller.balance;
        uint256 devBefore = dev.balance;
        uint256 buyerBefore = buyer.balance;

        uint256 dealPayment = 1 ether;
        vm.prank(buyer);
        room.acceptDeal(id, dealPayment);

        DiligenceRoom.Deal memory d = room.getDeal(id);
        assertEq(uint8(d.state), uint8(DiligenceRoom.State.Accepted));

        uint256 devPayment = 0.1 ether + 0.001 ether;
        uint256 expectedRefund = budgetCap - dealPayment - devPayment;

        assertEq(room.pendingWithdrawals(seller), dealPayment);
        assertEq(room.pendingWithdrawals(dev), devPayment);
        assertEq(room.pendingWithdrawals(buyer), expectedRefund);

        vm.prank(seller);
        room.withdraw();
        room.withdraw();
        vm.prank(buyer);
        room.withdraw();

        assertEq(seller.balance - sellerBefore, dealPayment);
        assertEq(dev.balance - devBefore, devPayment);
        assertEq(buyer.balance - buyerBefore, expectedRefund);
    }

    function test_AcceptDeal_RevertingSellerCannotBlockSettlement() public {
        RevertingReceiver revertingSeller = new RevertingReceiver(room);
        uint256 id = revertingSeller.createDeal(reservePrice, expiry, artifactHash, tee);

        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.High, 0.1 ether);

        vm.prank(buyer);
        room.acceptDeal(id, 1 ether);

        DiligenceRoom.Deal memory d = room.getDeal(id);
        assertEq(uint8(d.state), uint8(DiligenceRoom.State.Accepted));
        assertEq(room.pendingWithdrawals(address(revertingSeller)), 1 ether);

        vm.expectRevert(DiligenceRoom.TransferFailed.selector);
        revertingSeller.withdraw();
        assertEq(room.pendingWithdrawals(address(revertingSeller)), 1 ether);
    }

    function test_AcceptDeal_RevertBelowReserve() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.High, 0.1 ether);

        vm.prank(buyer);
        vm.expectRevert(DiligenceRoom.PaymentBelowReserve.selector);
        room.acceptDeal(id, 0.1 ether); // below 0.5 ether reserve
    }

    function test_AcceptDeal_RevertAboveBudget() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.High, 0.1 ether);

        vm.prank(buyer);
        vm.expectRevert(DiligenceRoom.PaymentAboveBudget.selector);
        room.acceptDeal(id, budgetCap); // dealPayment + devPayment > budgetCap
    }

    function test_AcceptDeal_RevertNotBuyer() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.High, 0.1 ether);

        vm.prank(seller);
        vm.expectRevert(DiligenceRoom.NotBuyer.selector);
        room.acceptDeal(id, 1 ether);
    }

    // ── Reject ─────────────────────────────────────────────────────────

    function test_RejectDeal() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.Negligible, 0.05 ether);

        uint256 devBefore = dev.balance;
        uint256 buyerBefore = buyer.balance;

        vm.prank(buyer);
        room.rejectDeal(id);

        DiligenceRoom.Deal memory d = room.getDeal(id);
        assertEq(uint8(d.state), uint8(DiligenceRoom.State.Rejected));

        uint256 devPayment = 0.05 ether + 0.0005 ether;
        uint256 buyerRefund = budgetCap - devPayment;

        assertEq(room.pendingWithdrawals(dev), devPayment);
        assertEq(room.pendingWithdrawals(buyer), buyerRefund);

        room.withdraw();
        vm.prank(buyer);
        room.withdraw();

        assertEq(dev.balance - devBefore, devPayment);
        assertEq(buyer.balance - buyerBefore, buyerRefund);
    }

    // ── Expire ─────────────────────────────────────────────────────────

    function test_ExpireDeal_Created() public {
        uint256 id = _createDeal();
        vm.warp(expiry + 1);

        room.expireDeal(id);

        DiligenceRoom.Deal memory d = room.getDeal(id);
        assertEq(uint8(d.state), uint8(DiligenceRoom.State.Expired));
    }

    function test_ExpireDeal_Funded() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        vm.warp(expiry + 1);

        uint256 buyerBefore = buyer.balance;
        room.expireDeal(id);

        assertEq(room.pendingWithdrawals(buyer), budgetCap);

        vm.prank(buyer);
        room.withdraw();
        assertEq(buyer.balance - buyerBefore, budgetCap);
    }

    function test_ExpireDeal_Evaluated() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.Low, 0.02 ether);

        vm.warp(expiry + 1);

        uint256 devBefore = dev.balance;
        uint256 buyerBefore = buyer.balance;

        room.expireDeal(id);

        uint256 devPayment = 0.02 ether + 0.0002 ether;
        uint256 buyerRefund = budgetCap - devPayment;

        assertEq(room.pendingWithdrawals(dev), devPayment);
        assertEq(room.pendingWithdrawals(buyer), buyerRefund);

        room.withdraw();
        vm.prank(buyer);
        room.withdraw();

        assertEq(dev.balance - devBefore, devPayment);
        assertEq(buyer.balance - buyerBefore, buyerRefund);
    }

    function test_ExpireDeal_RevertNotExpired() public {
        uint256 id = _createDeal();
        _fundDeal(id);

        vm.expectRevert(DiligenceRoom.NotExpired.selector);
        room.expireDeal(id);
    }

    function test_ExpireDeal_RevertAlreadyResolved() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.High, 0.1 ether);

        vm.prank(buyer);
        room.acceptDeal(id, 1 ether);

        vm.warp(expiry + 1);
        vm.expectRevert();
        room.expireDeal(id);
    }

    function test_Withdraw_RevertNothingToWithdraw() public {
        vm.expectRevert(DiligenceRoom.NothingToWithdraw.selector);
        room.withdraw();
    }

    // ── Full lifecycle ─────────────────────────────────────────────────

    function test_FullLifecycle_Accept() public {
        // 1. Seller creates deal
        uint256 id = _createDeal();

        // 2. Buyer funds
        _fundDeal(id);

        // 3. TEE evaluates
        _submitResult(id, DiligenceRoom.ScoreBand.Exceptional, 0.2 ether);

        // 4. Buyer accepts at reserve price
        vm.prank(buyer);
        room.acceptDeal(id, reservePrice);

        DiligenceRoom.Deal memory d = room.getDeal(id);
        assertEq(uint8(d.state), uint8(DiligenceRoom.State.Accepted));
    }

    function test_FullLifecycle_Reject() public {
        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.Negligible, 0.01 ether);

        vm.prank(buyer);
        room.rejectDeal(id);

        DiligenceRoom.Deal memory d = room.getDeal(id);
        assertEq(uint8(d.state), uint8(DiligenceRoom.State.Rejected));
    }

    // ── Fuzz ───────────────────────────────────────────────────────────

    function testFuzz_Settlement(uint256 payment, uint256 compute) public {
        // Bound inputs to reasonable ranges
        payment = bound(payment, reservePrice, 1 ether);
        compute = bound(compute, 0, 0.3 ether);
        uint256 fee = (compute * 100) / 10000;

        // Ensure total doesn't exceed budget
        vm.assume(payment + compute + fee <= budgetCap);

        uint256 id = _createDeal();
        _fundDeal(id);
        _submitResult(id, DiligenceRoom.ScoreBand.Medium, compute);

        uint256 totalBefore = seller.balance + dev.balance + buyer.balance;

        vm.prank(buyer);
        room.acceptDeal(id, payment);

        uint256 totalPending =
            room.pendingWithdrawals(seller) +
            room.pendingWithdrawals(dev) +
            room.pendingWithdrawals(buyer);

        assertEq(totalPending, budgetCap);
        assertEq(seller.balance + dev.balance + buyer.balance - totalBefore, 0);
    }

    // Allow receiving ETH (developer is this contract in tests)
    receive() external payable {}
}
