# 🔐 zkCredit: Zero-Knowledge Undercollateralized DeFi Lending

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Solidity](https://img.shields.io/badge/Solidity-%5E0.8.0-363636.svg)
![Circom](https://img.shields.io/badge/Circom-2.0.0-orange.svg)
![Network](https://img.shields.io/badge/Network-Sepolia_Testnet-purple.svg)

**zkCredit** is a fully on-chain, Zero-Knowledge Machine Learning (zkML) credit protocol. It allows users to unlock undercollateralized DeFi loans by proving their creditworthiness based on historical on-chain behavior—**without ever exposing their actual wallet address, balance, or transaction history to the public blockchain.**

---

## The Core Problem
Current DeFi lending (like Aave or Compound) is entirely overcollateralized. To borrow $100, a user must lock up $150. This is trustless, but highly capital inefficient. 

**The Solution:** zkCredit acts as a privacy-preserving Credit Oracle. It uses an off-chain Machine Learning model trained on actual Aave V3 liquidation data to assess wallet risk. Users generate a zk-SNARK proof of their risk score locally, and a Solidity Smart Contract verifies the proof to dynamically grant undercollateralized credit lines (up to 50% LTV).

---

## Architecture Overview

The protocol is divided into four distinct engineering layers:

1. **The Data Engine (`zk_credit_trainer.py`)**
   - Bypasses traditional GraphQL limits by streaming raw blockchain state via RPC.
   - Reconstructs Aave V3 lending/liquidation history into a clean dataset.
   - Trains a memory-efficient `SGDClassifier` using incremental learning to predict liquidation risk.

2. **The Cryptography Compiler (`zk_compiler.py`)**
   - A custom Python compiler that translates standard floating-point ML weights into cryptographic constraints.
   - **Quantization:** Multiplies floats by a scale factor ($2^{16}$) to convert them to integers.
   - **Finite Field Arithmetic:** Wraps negative weights around the massive BabyJubJub prime ($p = 2188824287...$) to ensure compatibility with Zero-Knowledge arithmetic circuits.

3. **The Proving Layer (Circom & SnarkJS)**
   - Automatically generates a `circuit.circom` file hardcoded with the ML model's weights.
   - Users input their private financial parameters locally to generate a Groth16 zk-SNARK proof (`proof.json`).
   - The user's actual data remains entirely off-chain. Only a mathematically verified $Z$ Score is made public.

4. **The On-Chain Protocol (Solidity)**
   - **`Groth16Verifier.sol`**: An auto-generated smart contract that mathematically verifies the user's zk-proof against the trusted setup parameters.
   - **`zkCreditPool.sol`**: The actual DeFi lending pool. It unwraps the finite-field $Z$ Score, enforces strict risk thresholds, prevents replay attacks using nullifier logic, and dynamically allocates USDC credit limits based on calculated risk tiers.

---

## Live Deployments (Sepolia Testnet)

The protocol is currently live and verified on the Ethereum Sepolia Testnet.

* **Groth16 Verifier Contract:** [`0xb468F68D204999Aa996D84131Ae9941B74e1F5BE`](https://sepolia.etherscan.io/address/0xb468F68D204999Aa996D84131Ae9941B74e1F5BE)
* **ZK Credit Pool Contract:** [`0xbdb01c43Bd2A004230FCb51F4823D9dA9Fd52337`](https://sepolia.etherscan.io/address/0xbdb01c43Bd2A004230FCb51F4823D9dA9Fd52337)

### Proof of Execution
* **Successful zkML Verification Transaction:** [`0xcb08de99fce676ca83b284a747ff49aba540a11645c828c73304b31807bed6b1`](https://sepolia.etherscan.io/tx/0xcb08de99fce676ca83b284a747ff49aba540a11645c828c73304b31807bed6b1)
  * *Note: In this transaction, a user successfully submits a Groth16 proof, the Bouncer contract verifies it, and the Pool grants a 50% LTV credit line based on a verified negative $Z$ score, all while keeping the underlying collateral parameters hidden.*

---

## Technical Highlights & Gas Optimizations

* **Off-Chain Thresholds:** Proving inequalities (e.g., $Z < 0$) inside a ZK circuit requires heavy bit-decomposition gadgets, exploding proof generation time. To optimize gas and compute, the circuit strictly calculates the raw $Z$ score and outputs it as a public signal. The `< 0` inequality check is deferred to the Solidity smart contract, where the operation costs practically zero gas.
* **Negative Number Unwrapping:** Because Solidity does not natively understand finite-field wrapped prime numbers, the smart contract utilizes the formula $P - Z$ to unwrap the BabyJubJub prime and extract the exact negative risk score natively on-chain.
* **EVM Trace & Data Privacy:** The calculation of the ML risk score and the Groth16 proof generation occurs 100% client-side, meaning the user's raw financial data never touches the RPC mempool. When the proof is submitted on-chain, the transaction payload contains only the mathematical proof and the public Z-score. Furthermore, to optimize gas, the `Groth16Verifier` is strictly utilized via `view` calls from the `zkCreditPool`. Therefore, the Verifier contract's public transaction history remains empty, as all EVM state changes and gas consumption are intentionally routed through the Pool contract.

---

## Quick Start (Local Proof Generation)

To generate a zero-knowledge credit proof locally:

```bash
# 1. Install dependencies
npm install -g snarkjs
cargo install --path circom

# 2. Compile the mathematical circuit
circom circuit.circom --r1cs --wasm --sym

# 3. Create your private data input (input.json)
echo '{"X": [150, 12, 5, 0]}' > input.json

# 4. Compute the Witness and Generate the Proof
node circuit_js/generate_witness.js circuit_js/circuit.wasm input.json witness.wtns
snarkjs groth16 prove circuit_final.zkey witness.wtns proof.json public.json

# 5. Format calldata for Ethereum Smart Contract
snarkjs zkey export soliditycalldata public.json proof.json
