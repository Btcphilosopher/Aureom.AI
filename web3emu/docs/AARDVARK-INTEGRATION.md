# Aardvark Imaging integration (recipe, not built)

Section 52 of the spec asks for a clean interface letting Aardvark
Imaging simulate tokenized artwork, ownership, transfers, provenance,
digital certificates, wallet identity and transaction history - entirely
locally. Aardvark itself is not part of this repository, so this
document is a **recipe** for the integration, built entirely on
primitives that already exist in `web3emu-contract`/`web3emu-core` -
nothing here is a stub pretending to be a real bridge.

```text
AARDVARK ARTWORK
      |
      v
VECTOR OBJECT              (Aardvark's own representation - out of scope here)
      |
      v
ASSET ID                   a stable identifier Aardvark already assigns
      |
      v
WEB3EMU TOKEN               an NFT minted via web3emu-contract::nft
      |
      v
OWNER                       the minting recipient's Address
      |
      v
TRANSFER                    web3emu tx call --contract <nft> --method transfer ...
      |
      v
LEDGER                      the resulting EmulatorBlock/TransactionReceipt/EventLog history
```

## Concretely

1. Deploy one NFT contract per Aardvark collection (or one shared
   contract with metadata URIs disambiguating pieces):

   ```bash
   web3emu contract deploy-nft --name "Aardvark Gallery" --symbol AARD --from Treasury
   ```

2. On each artwork export, mint a token whose `tokenURI` is Aardvark's
   own asset identifier or a content-addressed pointer to it - **never**
   raw image bytes (section 28 explicitly rules this out; keep imagery
   in Aardvark's own storage):

   ```bash
   web3emu tx call --contract <nft> --method mint --from Treasury \
     --args "address:<recipient>,bytes:<hex-encoded asset id or URI>"
   ```

3. Ownership queries (`ownerOf`), provenance (the full transaction
   history for a `tokenId`, via `web3emu-rpc`'s `eth_getLogs` filtered by
   the NFT's address and the `Transfer` event, or `web3emu trace
   <tx-hash>` for a single transfer's detail), and transfers
   (`tx call --method transfer`) all go through the same RPC/CLI surface
   documented in `docs/RPC.md` and `docs/CONTRACTS.md` - Aardvark needs
   no bespoke protocol, just a JSON-RPC client.

4. "Digital certificate" and "wallet identity" map directly onto
   `web3emu-wallet`'s `EmulatorWallet` (a certificate is simply proof of
   control of the owning address, provable the same way any Web3 wallet
   proves it - by producing a valid signature).

Everything above is achievable today with the existing CLI/RPC/Rust API
and requires no changes to `web3emu-core`. What's missing is only the
Aardvark-side client code, which lives in Aardvark's own repository, not
here.
