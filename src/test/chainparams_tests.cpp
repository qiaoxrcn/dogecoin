// Copyright (c) 2026 The Dogecoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "base58.h"
#include "chainparams.h"
#include "key.h"
#include "test/test_bitcoin.h"
#include "util.h"
#include "utilstrencodings.h"

#include <boost/test/unit_test.hpp>
#include <map>

extern std::map<std::string, std::string> mapArgs;

struct ChainParamsTestingSetup : BasicTestingSetup {
    std::map<std::string, std::string> savedArgs;
    ChainParamsTestingSetup() : savedArgs(mapArgs) { mapArgs.clear(); }
    ~ChainParamsTestingSetup() {
        mapArgs = savedArgs;
        SelectParams(CBaseChainParams::MAIN);
    }
};

BOOST_FIXTURE_TEST_SUITE(chainparams_tests, ChainParamsTestingSetup)

BOOST_AUTO_TEST_CASE(regtest_testnet_selection)
{
    ForceSetArg("-regtesttestnet", "1");
    BOOST_CHECK_THROW(ChainNameFromCommandLine(), std::runtime_error);
    ForceSetArg("-testnet", "1");
    BOOST_CHECK_THROW(ChainNameFromCommandLine(), std::runtime_error);
    ForceSetArg("-regtest", "1");
    BOOST_CHECK_THROW(ChainNameFromCommandLine(), std::runtime_error);
    ForceSetArg("-testnet", "0");
    BOOST_CHECK_EQUAL(ChainNameFromCommandLine(), CBaseChainParams::REGTEST);
    SelectParams(ChainNameFromCommandLine());
    BOOST_CHECK_EQUAL(BaseParams().DataDir(), "regtest-testnet");
    BOOST_CHECK_EQUAL(BaseParams().RPCPort(), 18332);
    BOOST_CHECK_EQUAL(Params().NetworkIDString(), "regtest");

    const CChainParams& compatible = Params();
    const CChainParams& testnet = Params(CBaseChainParams::TESTNET);
    BOOST_CHECK_EQUAL_COLLECTIONS(compatible.MessageStart(), compatible.MessageStart() + 4,
                                 testnet.MessageStart(), testnet.MessageStart() + 4);
    for (int i = 0; i < CChainParams::MAX_BASE58_TYPES; ++i) {
        auto type = static_cast<CChainParams::Base58Type>(i);
        BOOST_CHECK(compatible.Base58Prefix(type) == testnet.Base58Prefix(type));
    }
    BOOST_CHECK(compatible.MineBlocksOnDemand());
    BOOST_CHECK(!compatible.MiningRequiresPeers());
    BOOST_CHECK(compatible.DNSSeeds().empty());
    BOOST_CHECK(compatible.FixedSeeds().empty());
    BOOST_CHECK_EQUAL(compatible.GetDefaultPort(), 18444);

    ForceSetArg("-regtesttestnet", "0");
    SelectParams(CBaseChainParams::REGTEST);
    BOOST_CHECK_EQUAL(BaseParams().DataDir(), "regtest");
    BOOST_CHECK_EQUAL(Params().MessageStart()[0], 0xfa);
    BOOST_CHECK_EQUAL(Params().Base58Prefix(CChainParams::PUBKEY_ADDRESS)[0], 111);
    BOOST_CHECK_EQUAL(Params().Base58Prefix(CChainParams::SECRET_KEY)[0], 239);
    BOOST_CHECK(compatible.GenesisBlock().GetHash() == Params().GenesisBlock().GetHash());
    for (uint32_t height : {0, 9, 10, 19, 20, 1000}) {
        const auto& original = Params().GetConsensus(height);
        const auto& actual = compatible.GetConsensus(height);
        BOOST_CHECK(actual.powLimit == original.powLimit);
        BOOST_CHECK(actual.fPowNoRetargeting);
        BOOST_CHECK_EQUAL(actual.nCoinbaseMaturity, original.nCoinbaseMaturity);
        BOOST_CHECK_EQUAL(actual.nHeightEffective, original.nHeightEffective);
        BOOST_CHECK_EQUAL(actual.fAllowLegacyBlocks, original.fAllowLegacyBlocks);
    }
}

BOOST_AUTO_TEST_CASE(regtest_testnet_key_roundtrip)
{
    const auto seed = ParseHex("000102030405060708090a0b0c0d0e0f");
    CExtKey master;
    master.SetMaster(seed.data(), seed.size());
    SelectParams(CBaseChainParams::TESTNET);
    const std::string address = CBitcoinAddress(master.key.GetPubKey().GetID()).ToString();
    const std::string secret = CBitcoinSecret(master.key).ToString();
    const std::string xpub = CBitcoinExtPubKey(master.Neuter()).ToString();
    const std::string xprv = CBitcoinExtKey(master).ToString();

    ForceSetArg("-regtesttestnet", "1");
    SelectParams(CBaseChainParams::REGTEST);
    BOOST_CHECK_EQUAL(CBitcoinAddress(master.key.GetPubKey().GetID()).ToString(), address);
    BOOST_CHECK_EQUAL(CBitcoinSecret(master.key).ToString(), secret);
    BOOST_CHECK_EQUAL(CBitcoinExtPubKey(master.Neuter()).ToString(), xpub);
    BOOST_CHECK_EQUAL(CBitcoinExtKey(master).ToString(), xprv);
    BOOST_CHECK(CBitcoinAddress(address).IsValid());
    CBitcoinSecret decodedSecret;
    BOOST_REQUIRE(decodedSecret.SetString(secret));
    BOOST_CHECK(decodedSecret.GetKey().GetPubKey() == master.key.GetPubKey());
    BOOST_CHECK(CBitcoinExtKey(xprv).GetKey() == master);
    BOOST_CHECK(CBitcoinExtPubKey(xpub).GetKey() == master.Neuter());

    ForceSetArg("-regtesttestnet", "0");
    SelectParams(CBaseChainParams::REGTEST);
    BOOST_CHECK(!CBitcoinAddress(address).IsValid());
    BOOST_CHECK(!decodedSecret.SetString(secret));
}

BOOST_AUTO_TEST_SUITE_END()
