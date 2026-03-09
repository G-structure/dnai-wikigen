// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {DiligenceRoom} from "../src/DiligenceRoom.sol";

contract DiligenceRoomScript is Script {
    function run() public {
        vm.startBroadcast();

        DiligenceRoom room = new DiligenceRoom();
        console.log("DiligenceRoom deployed at:", address(room));
        console.log("Developer (fee recipient):", room.developer());

        vm.stopBroadcast();
    }
}
