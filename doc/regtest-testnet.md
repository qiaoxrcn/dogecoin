# Regtest with testnet formats

This build adds `-regtesttestnet`, used together with `-regtest`, for private
block explorer integration and reorganization tests. All regtest consensus and
mining behavior is retained. Only address/key encoding prefixes and message magic
are taken from testnet. Normal mainnet, testnet and regtest remain available.

| Parameter | Normal regtest | With `-regtesttestnet` |
| --- | --- | --- |
| P2PKH address version | `0x6f` (111) | `0x71` (113), testnet |
| P2SH address version | `0xc4` (196) | `0xc4` (196), testnet |
| WIF private key version | `0xef` (239) | `0xf1` (241), testnet |
| Extended public key version | `043587cf` (`tpub`) | unchanged, testnet |
| Extended private key version | `04358394` (`tprv`) | unchanged, testnet |
| P2P and block/undo file magic (byte order) | `fa bf b5 da` | `fc c1 b7 dc`, testnet |
| Data subdirectory | `regtest/` | `regtest-testnet/` |
| Default P2P / RPC ports | 18444 / 18332 | 18444 / 18332 |
| RPC chain name | `regtest` | `regtest` |

Raw secp256k1 public keys already use the same serialization on all networks:
33-byte compressed keys (`02`/`03`) or 65-byte uncompressed keys (`04`). Private
scalar bytes are also network-independent; WIF is their network-specific encoding.

## Build on GitHub

The **Regtest with testnet formats** Actions workflow builds Linux x86_64 binaries
with wallet and ZMQ support on Ubuntu 22.04. It runs the C++ unit tests, a new
testnet-format/reorg integration test, and the existing regtest invalidation test.
The artifact is uploaded only after all those steps succeed.

Push the changes to `master` or a branch named `regtest-testnet/<name>` in a
repository where you have write access and Actions is enabled. Once this workflow
exists on the repository's default branch, it can also be run with the Actions
page's **Run workflow** button or:

```bash
gh workflow run regtest-testnet.yml --repo OWNER/dogecoin --ref BRANCH
gh run list --repo OWNER/dogecoin --workflow regtest-testnet.yml
gh run download RUN_ID --repo OWNER/dogecoin
```

The downloadable artifact contains a tar archive with `dogecoind`, `dogecoin-cli`,
`dogecoin-tx`, this document, a commit ID, and a runtime library list. `SHA256SUMS`
checks the archive. These are dynamically linked Ubuntu 22.04 binaries, not a
portable static release. Install matching runtime libraries on the target host;
consult `runtime-libraries.txt` (Boost, Berkeley DB 5.3, OpenSSL, libevent, ZMQ).
The repository's existing CI also provides builds for other platforms.

## Start a private explorer node

Use a fresh data directory. Do not move an existing regtest/testnet wallet or
block database into the new subdirectory.

```bash
mkdir -p "$PWD/explorer-data"
./bin/dogecoind -regtest -regtesttestnet -datadir="$PWD/explorer-data" \
  -daemon -txindex=1 -connect=0 -dnsseed=0 -listenonion=0 -bind=127.0.0.1

./bin/dogecoin-cli -regtest -regtesttestnet -datadir="$PWD/explorer-data" getnewaddress
./bin/dogecoin-cli -regtest -regtesttestnet -datadir="$PWD/explorer-data" generate 65
```

Alternatively, place `regtest=1` and `regtesttestnet=1` in `dogecoin.conf` in the
base data directory. The CLI needs the same settings to find the RPC cookie under
`regtest-testnet/`. Both options are also supported by `dogecoin-tx` and the GUI
through shared chain parameter selection. `-regtesttestnet` without `-regtest`, or
combining `-regtest` and `-testnet`, is rejected.

Configure the explorer's testnet address/key and magic settings, but point its
RPC and P2P endpoints at your private nodes. Genesis remains regtest:

```text
3d2160a3b5dc4a9d62e7e66a295f70313ac808440ef7400d6c0772171ce973a5
```

If the explorer checks genesis, chain name, proof of work, checkpoints, AuxPoW
activation, or coinbase maturity, configure it for regtest consensus as well.
Matching magic and address prefixes alone cannot bypass those checks. Regtest
coinbase maturity is 60 blocks; AuxPoW activates at height 20. Generated coins
belong to this private chain and cannot be spent on public testnet.

There are no DNS or fixed seeds in this mode. Keep peer connections private:
because magic is shared with public testnet, it no longer separates those
networks at the message-header level. Use explicit private peers and firewall or
loopback bindings. Each peer in the test must enable the same mode. Two local
nodes need different data directories and explicit distinct RPC/P2P ports.

## Reproduce reorg

For a single node, save a block hash, use `invalidateblock HASH` to detach that
block and its descendants, and use `generate N` to mine a replacement branch.
`reconsiderblock HASH` makes the old branch eligible again, subject to chain work.

For a real competing-chain test:

1. Start two nodes with both flags, connect them and mine a common history.
2. Disable networking on node B with `setnetworkactive false`.
3. Send a transaction on A and mine two blocks to confirm it.
4. Mine three blocks on B, then enable networking and reconnect the peers.
5. A adopts B's greater-work branch. Its detached blocks have `confirmations=-1`;
   an eligible nonconflicting transaction returns to the mempool and can be mined
   again. The explorer should remove its old confirmations and index the new branch.

The new `qa/rpc-tests/regtest_testnet.py` automates this scenario, checks transaction
reconfirmation, validates testnet key encodings and P2P/disk magic, and restarts
the nodes to verify persistence. Execution happens in GitHub Actions.
