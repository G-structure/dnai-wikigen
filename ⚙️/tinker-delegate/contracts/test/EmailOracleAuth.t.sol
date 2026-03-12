// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";

import {EmailOracleAuth} from "../src/EmailOracleAuth.sol";
import {IAppAuth} from "../src/interfaces/IAppAuth.sol";

contract EmailOracleAuthTest is Test {
    EmailOracleAuth internal auth;

    address internal owner = makeAddr("owner");
    address internal other = makeAddr("other");
    address internal manager = makeAddr("manager");
    address internal consumer = makeAddr("consumer");

    bytes32 internal initialComposeHash = keccak256("oracle-compose-v1");
    bytes32 internal nextComposeHash = keccak256("oracle-compose-v2");
    bytes32 internal deviceId = keccak256("device-1");
    bytes32 internal consumerComposeHash = keccak256("delegate-compose-v1");

    function setUp() public {
        auth = new EmailOracleAuth(owner, 2 days, true, bytes32(0), initialComposeHash);
    }

    function _bootInfo(
        address appId,
        bytes32 composeHash,
        bytes32 bootDeviceId
    ) internal pure returns (IAppAuth.AppBootInfo memory info) {
        info = IAppAuth.AppBootInfo({
            appId: appId,
            composeHash: composeHash,
            instanceId: address(0x1234),
            deviceId: bootDeviceId,
            mrAggregated: bytes32(0),
            mrSystem: bytes32(0),
            osImageHash: bytes32(0),
            tcbStatus: "UpToDate",
            advisoryIds: new string[](0)
        });
    }

    function test_InitialComposeHashIsAllowed() public {
        (bool allowed, string memory reason) = auth.isAppAllowed(
            _bootInfo(address(auth), initialComposeHash, bytes32(0))
        );

        assertTrue(allowed);
        assertEq(reason, "");
    }

    function test_IsAppAllowed_RejectsWrongAppId() public {
        (bool allowed, string memory reason) = auth.isAppAllowed(
            _bootInfo(address(0xBEEF), initialComposeHash, bytes32(0))
        );

        assertFalse(allowed);
        assertEq(reason, "App ID mismatch");
    }

    function test_ProposeAndActivateOracleComposeHash() public {
        vm.prank(owner);
        auth.proposeOracleComposeHash(nextComposeHash);

        vm.warp(block.timestamp + 2 days);
        auth.activateOracleComposeHash(nextComposeHash);

        (bool allowed, string memory reason) = auth.isAppAllowed(
            _bootInfo(address(auth), nextComposeHash, bytes32(0))
        );
        assertTrue(allowed);
        assertEq(reason, "");
    }

    function test_ActivateOracleComposeHash_RevertTooEarly() public {
        vm.prank(owner);
        auth.proposeOracleComposeHash(nextComposeHash);

        vm.expectRevert(
            abi.encodeWithSelector(EmailOracleAuth.ActivationTooEarly.selector, block.timestamp + 2 days)
        );
        auth.activateOracleComposeHash(nextComposeHash);
    }

    function test_DeviceRestriction() public {
        vm.startPrank(owner);
        auth.setAllowAnyDevice(false);
        auth.addDevice(deviceId);
        vm.stopPrank();

        (bool allowedWrongDevice, ) = auth.isAppAllowed(
            _bootInfo(address(auth), initialComposeHash, keccak256("other-device"))
        );
        assertFalse(allowedWrongDevice);

        (bool allowedRightDevice, ) = auth.isAppAllowed(
            _bootInfo(address(auth), initialComposeHash, deviceId)
        );
        assertTrue(allowedRightDevice);
    }

    function test_OwnerCanDelegateConsumerManagement() public {
        vm.prank(owner);
        auth.setConsumerManager(manager, true);

        vm.prank(manager);
        auth.addConsumerComposeHash(consumer, consumerComposeHash);

        assertTrue(auth.isConsumerAuthorized(consumer, consumerComposeHash));
        assertEq(auth.consumerComposeHashCount(consumer), 1);
    }

    function test_ManagerCannotChangeOraclePolicy() public {
        vm.prank(owner);
        auth.setConsumerManager(manager, true);

        vm.prank(manager);
        vm.expectRevert(EmailOracleAuth.NotOwner.selector);
        auth.proposeOracleComposeHash(nextComposeHash);
    }

    function test_FreezeOracleCodeAuth_StillAllowsConsumerUpdates() public {
        vm.prank(owner);
        auth.freezeOracleCodeAuth();

        vm.prank(owner);
        auth.addConsumerComposeHash(consumer, consumerComposeHash);

        assertTrue(auth.oracleCodeFrozen());
        assertTrue(auth.isConsumerAuthorized(consumer, consumerComposeHash));

        vm.prank(owner);
        vm.expectRevert(EmailOracleAuth.OracleCodeFrozen.selector);
        auth.proposeOracleComposeHash(nextComposeHash);
    }

    function test_FreezeConsumerRegistry_BlocksOwnerAndManager() public {
        vm.startPrank(owner);
        auth.setConsumerManager(manager, true);
        auth.addConsumerComposeHash(consumer, consumerComposeHash);
        auth.freezeConsumerRegistry();
        vm.stopPrank();

        vm.prank(owner);
        vm.expectRevert(EmailOracleAuth.ConsumerRegistryFrozen.selector);
        auth.removeConsumerComposeHash(consumer, consumerComposeHash);

        vm.prank(manager);
        vm.expectRevert(EmailOracleAuth.ConsumerRegistryFrozen.selector);
        auth.addConsumerComposeHash(consumer, keccak256("delegate-compose-v2"));
    }

    function test_RemoveConsumerComposeHashRevokesAuthorization() public {
        vm.startPrank(owner);
        auth.addConsumerComposeHash(consumer, consumerComposeHash);
        auth.removeConsumerComposeHash(consumer, consumerComposeHash);
        vm.stopPrank();

        assertFalse(auth.isConsumerAuthorized(consumer, consumerComposeHash));
        assertEq(auth.consumerComposeHashCount(consumer), 0);
    }

    function test_FreezeOracleCodeAuth_BlocksDeviceMutations() public {
        vm.prank(owner);
        auth.freezeOracleCodeAuth();

        vm.prank(owner);
        vm.expectRevert(EmailOracleAuth.OracleCodeFrozen.selector);
        auth.addDevice(deviceId);
    }
}
