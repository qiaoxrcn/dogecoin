#!/usr/bin/env python3
# Copyright (c) 2026 The Dogecoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""Check testnet encodings, wire/disk magic and transaction reorg on regtest."""

import hashlib
import os
import socket
import struct
import subprocess
import time

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (
    assert_equal, connect_nodes_bi, p2p_port, start_node, sync_blocks,
    sync_mempools,
)


def base58check(payload):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    number = int.from_bytes(payload + checksum, "big")
    result = ""
    while number:
        number, digit = divmod(number, 58)
        result = alphabet[digit] + result
    return "1" * (len(payload) - len(payload.lstrip(b"\0"))) + result


class RegtestTestnetTest(BitcoinTestFramework):
    def __init__(self):
        super().__init__()
        self.setup_clean_chain = True
        self.num_nodes = 4

    def setup_network(self):
        self.nodes = []
        for i in range(self.num_nodes):
            args = ["-connect=0", "-dnsseed=0", "-txindex=1"]
            if i < 2:
                args += ["-regtesttestnet=1"]
            elif i == 2:
                args += ["-regtest=0", "-testnet=1"]
            self.nodes.append(start_node(i, self.options.tmpdir, args))

    def check_wire_magic(self):
        # Minimal version message, using testnet magic independently of the node.
        magic = bytes.fromhex("fcc1b7dc")
        address = struct.pack("<Q", 1) + bytes(16) + struct.pack(">H", 18444)
        version = (struct.pack("<iQq", 70015, 1, int(time.time())) +
                   address + address + struct.pack("<Q", 123456) +
                   b"\x00" + struct.pack("<i?", 0, True))
        checksum = hashlib.sha256(hashlib.sha256(version).digest()).digest()[:4]
        packet = magic + b"version".ljust(12, b"\0") + struct.pack("<I", len(version)) + checksum + version
        with socket.create_connection(("127.0.0.1", p2p_port(0)), timeout=10) as peer:
            peer.sendall(packet)
            header = b""
            while len(header) < 24:
                chunk = peer.recv(24 - len(header))
                assert chunk, "Peer closed before returning a version header"
                header += chunk
            assert_equal(header[:4], magic)
            assert_equal(header[4:16].rstrip(b"\0"), b"version")

    def run_test(self):
        node, other, testnet, original = self.nodes
        print("Check testnet WIF, P2PKH, P2SH and public key compatibility")
        # Public test vector: private scalar 1 (never use for real funds).
        wif = base58check(b"\xf1" + (1).to_bytes(32, "big") + b"\x01")
        pubkey = "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
        keyhash = hashlib.new("ripemd160", hashlib.sha256(bytes.fromhex(pubkey)).digest()).digest()
        address = base58check(b"\x71" + keyhash)
        for rpc in (node, testnet):
            rpc.importprivkey(wif, "format-test", False)
            assert_equal(rpc.dumpprivkey(address), wif)
            assert_equal(rpc.validateaddress(address)["pubkey"], pubkey)
        assert_equal(node.createmultisig(1, [pubkey]), testnet.createmultisig(1, [pubkey]))
        assert not original.validateaddress(address)["isvalid"]
        assert_equal(node.getblockchaininfo()["chain"], "regtest")
        assert_equal(node.getblockhash(0), original.getblockhash(0))
        assert node.getblockhash(0) != testnet.getblockhash(0)
        self.check_wire_magic()

        print("Check CLI configuration and invalid flag combinations")
        cli = os.getenv("DOGECOINCLI", os.path.join(self.options.srcdir, "dogecoin-cli"))
        datadir = os.path.join(self.options.tmpdir, "node0")
        output = subprocess.check_output([cli, "-datadir=" + datadir, "-regtesttestnet", "getblockcount"])
        assert_equal(int(output), 0)
        for args in (["-regtest=0", "-regtesttestnet"],
                     ["-regtest", "-testnet", "-regtesttestnet"]):
            result = subprocess.run([cli, "-datadir=" + datadir] + args + ["getblockcount"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert result.returncode != 0
            assert b"requires -regtest" in result.stderr or b"Invalid combination" in result.stderr

        print("Mine spendable coins, split peers and create competing branches")
        node.generate(65)
        connect_nodes_bi(self.nodes, 0, 1)
        sync_blocks(self.nodes[:2])
        other.setnetworkactive(False)
        txid = node.sendtoaddress(other.getnewaddress(), 10)
        old_branch = node.generate(2)
        assert_equal(node.gettransaction(txid)["confirmations"], 2)
        new_branch = other.generate(3)
        other.setnetworkactive(True)
        connect_nodes_bi(self.nodes, 0, 1)
        sync_blocks(self.nodes[:2])
        sync_mempools(self.nodes[:2])
        assert_equal(node.getbestblockhash(), new_branch[-1])
        assert_equal(node.getblockcount(), 68)
        assert_equal(node.getblock(old_branch[0])["confirmations"], -1)
        assert_equal(node.gettransaction(txid)["confirmations"], 0)
        assert txid in node.getrawmempool()
        node.generate(1)
        sync_blocks(self.nodes[:2])
        assert_equal(node.gettransaction(txid)["confirmations"], 1)

        print("Check invalidation/reconsideration and persisted block magic")
        tip = node.getbestblockhash()
        node.invalidateblock(tip)
        assert_equal(node.getblockcount(), 68)
        node.reconsiderblock(tip)
        assert_equal(node.getbestblockhash(), tip)
        for i in range(2):
            self.stop_node(i)
            root = os.path.join(self.options.tmpdir, "node" + str(i))
            with open(os.path.join(root, "regtest-testnet", "blocks", "blk00000.dat"), "rb") as blocks:
                assert_equal(blocks.read(4), bytes.fromhex("fcc1b7dc"))
            assert not os.path.exists(os.path.join(root, "regtest", "blocks"))
            self.nodes[i] = start_node(i, self.options.tmpdir, ["-regtesttestnet", "-connect=0", "-txindex=1"])
            assert_equal(self.nodes[i].getbestblockhash(), tip)


if __name__ == "__main__":
    RegtestTestnetTest().main()
