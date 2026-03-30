// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// 1. We define an interface so our Pool can talk to your deployed Verifier
interface IGroth16Verifier {
    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[1] calldata _pubSignals
    ) external view returns (bool);
}

contract ZKCreditPool {
    IGroth16Verifier public verifier;
    
    // The BabyJubJub Prime Number
    uint256 constant PRIME = 21888242871839275222246405745257275088548364400416034343698204186575808495617;
    
    // Track user deposits and active credit lines
    mapping(address => uint256) public ethCollateral;
    mapping(address => uint256) public usdcCreditLimit;
    mapping(address => bool) public hasUsedProof;

    // We pass the address of your deployed Verifier into this contract
    constructor(address _verifierAddress) {
        verifier = IGroth16Verifier(_verifierAddress);
    }

    // 2. The Main Function: Users deposit ETH and submit their ZK Proof simultaneously
    function requestRiskAdjustedLoan(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[1] calldata _pubSignals
    ) external payable {
        
        // Security Check: Ensure they deposited ETH collateral
        require(msg.value > 0, "Must deposit ETH collateral");
        
        // Security Check: Prevent replay attacks (using the same proof twice)
        // Note: In production, we would use a cryptographic "nullifier" inside the circuit.
        require(!hasUsedProof[msg.sender], "Proof already used for a loan");

        // 3. THE BOUNCER: Ask the Verifier if the math is mathematically flawless
        bool isValid = verifier.verifyProof(_pA, _pB, _pC, _pubSignals);
        require(isValid, "ZK Proof is invalid! Nice try.");

        // 4. DECODE THE Z-SCORE
        uint256 rawZ = _pubSignals[0];
        
        // If the score is less than half the prime, it's a positive number (High Risk)
        if (rawZ < PRIME / 2) {
            revert("Z-Score > 0: High Risk of Liquidation. Loan Denied.");
        }

        // If we pass the revert, the score is negative (Good Risk). Let's unwrap it.
        uint256 absoluteZScore = PRIME - rawZ;

        // 5. TIERED RISK LOGIC (Dynamic LTV based on the ML Model's output)
        uint256 creditGranted = 0;

        // Assuming a dummy ETH price of $3000 for calculation ease
        uint256 collateralValueUSD = (msg.value * 3000) / 1 ether; 

        // Because our Python weights were massive, our quantized absoluteZScore is very high (e.g., billions).
        // We will use conservative absolute thresholds based on your model's output.
        if (absoluteZScore > 100000000000) {
            // Prime Whale Tier: 50% LTV
            creditGranted = (collateralValueUSD * 50) / 100;
        } else if (absoluteZScore > 50000000000) {
            // Good Tier: 25% LTV
            creditGranted = (collateralValueUSD * 25) / 100;
        } else {
            // Standard Tier: 10% LTV
            creditGranted = (collateralValueUSD * 10) / 100;
        }

        // 6. UPDATE STATE
        ethCollateral[msg.sender] += msg.value;
        usdcCreditLimit[msg.sender] += creditGranted;
        hasUsedProof[msg.sender] = true;
    }

    // Helper function to check your credit limit
    function getMyCreditLimit() external view returns (uint256) {
        return usdcCreditLimit[msg.sender];
    }
}