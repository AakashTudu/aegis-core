import time
import requests
import numpy as np
from web3 import Web3
from sklearn.linear_model import SGDClassifier
from web3.middleware import ExtraDataToPOAMiddleware
import joblib
import os

# ==========================================
# 1. CONFIGURATION & CONNECTIONS
# ==========================================
# RPC Node (Alchemy, Infura, or QuickNode)
RPC_URL = "https://eth-mainnet.g.alchemy.com/v2/07EgKVF8YX-VrrPvpTONK"
w3 = Web3(Web3.HTTPProvider(RPC_URL))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

# Subgraph API URL (Requires your custom Subgraph for X features)
GRAPHQL_ENDPOINT = "https://api.v3.aave.com/graphql"

# Aave V3 Pool Contract Address (Mainnet)
AAVE_POOL_ADDRESS = w3.to_checksum_address("0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2")

# Keccak-256 Hashes
REPAY_EVENT_SIG = w3.keccak(text="Repay(address,address,address,uint256,bool)").hex()
LIQUIDATION_EVENT_SIG = w3.keccak(text="LiquidationCall(address,address,address,uint256,uint256,address,bool)").hex()

# ==========================================
# 2. MODEL INITIALIZATION (WITH RESUME LOGIC)
# ==========================================
MODEL_FILE = 'zkcredit_model.pkl'
classes = np.array([0, 1]) # 0 = Repay, 1 = Liquidation
BATCH_SIZE = 50 

if os.path.exists(MODEL_FILE):
    print(f"🧠 Found existing brain! Loading {MODEL_FILE}...")
    model = joblib.load(MODEL_FILE)
else:
    print("🧠 No existing brain found. Starting from a blank slate...")
    model = SGDClassifier(loss='log_loss', learning_rate='optimal', random_state=42)

# ==========================================
# 3. RPC FEATURE EXTRACTOR (THE TIME MACHINE)
# ==========================================
def extract_features_via_rpc(wallet_address, borrow_block):
    """
    Queries Alchemy directly to retrieve historical wallet state
    strictly BEFORE the loan was taken out to prevent Data Leakage.
    """
    try:
        # X1: Nonce (Total transactions sent by this wallet before the loan)
        # This is the ultimate on-chain proxy for Wallet Age / Experience
        nonce = w3.eth.get_transaction_count(wallet_address, block_identifier=borrow_block)
        
        # X2: ETH Balance (Capitalization before the loan)
        balance_wei = w3.eth.get_balance(wallet_address, block_identifier=borrow_block)
        balance_eth = float(w3.from_wei(balance_wei, 'ether'))
        
        # X3 & X4: To keep our 4-feature model intact without complex indexers, 
        # we will use derived metrics based on the first two.
        # X3: High nonce + high balance implies high holding power.
        derived_holding_power = (balance_eth * 10) / (nonce + 1)
        
        # X4: Constant placeholder (You can expand this later)
        x4_placeholder = 0.0 
        
        return [float(nonce), balance_eth, derived_holding_power, x4_placeholder]
        
    except Exception as e:
        print(f"RPC State Error for {wallet_address}: {e}")
        return None

# ==========================================
# 4. THE HISTORICAL STREAMING ENGINE
# ==========================================
def run_historical_training_pipeline():
    print("🚀 Initializing zkCredit Historical Pipeline...")
    if not w3.is_connected():
        raise ConnectionError("Failed to connect to RPC Node.")
    
    # Aave V3 deployed around block 16,500,000. 
    # We read in chunks of 2,000 to avoid overloading the RPC node.
    START_BLOCK = 16500000 
    CHUNK_SIZE = 10
    
    current_block = START_BLOCK
    target_block = w3.eth.block_number
    
    X_batch, Y_batch = [], []
    total_trained = 0
    
    print(f"🌊 Streaming history from block {START_BLOCK} to {target_block}...")

    # Run until we catch up to the present day
    while current_block < target_block:
        to_block = current_block+CHUNK_SIZE-1
        
        try:
            # Fetch thousands of blocks instantly
            logs = w3.eth.get_logs({
                'fromBlock': current_block,
                'toBlock': to_block,
                'address': AAVE_POOL_ADDRESS,
                'topics': [[REPAY_EVENT_SIG, LIQUIDATION_EVENT_SIG]]
            })

            for log in logs:
                event_sig = log['topics'][0].hex()
                
                if event_sig == LIQUIDATION_EVENT_SIG:
                    Y_label = 1
                    # In LiquidationCall, the user is topic[3]
                    raw_address = "0x" + log['topics'][3].hex()[-40:]
                else:
                    Y_label = 0
                    # In Repay, the user is topic[2]
                    raw_address = "0x" + log['topics'][2].hex()[-40:]
                
                # Convert the raw lowercase hex into an EIP-55 Checksum Address
                wallet_address = w3.to_checksum_address(raw_address)
                
                # Fetch block timestamp to rewind the clock
                block_info = w3.eth.get_block(log['blockNumber'])
                borrow_block = max(0, log['blockNumber'] - 216000)
                
                # Extract Features via The Graph
                print("Initiating Extract Features via RPC")
                X_features = extract_features_via_rpc(wallet_address, borrow_block)
                print(X_features)
                
                if X_features:
                    X_batch.append(X_features)
                    Y_batch.append(Y_label)
                
                # Incremental Training & Memory Flush
                print(f"Len(X_batch) = {len(X_batch)} and BATCH_SIZE = {BATCH_SIZE}")
                if len(X_batch) >= BATCH_SIZE:
                    model.partial_fit(X_batch, Y_batch, classes=classes)
                    total_trained += BATCH_SIZE
                    print(f"✅ Trained on {BATCH_SIZE} events. (Total Model Experience: {total_trained} loans). Memory flushed.")
                    
                    # Save the model state incrementally in case you need to stop the script
                    joblib.dump(model, 'zkcredit_model.pkl')
                    
                    X_batch, Y_batch = [], [] 
            
            # Move the window forward
            current_block = to_block + 1
            print(f"current block = {current_block}")
            
        except Exception as e:
            # Let's extract the exact error message from Alchemy
            import traceback
            error_msg = str(e)
            
            print(f"⚠️ Alchemy Error Details: {error_msg}")
            print(f"Cooling down Mac for 10 seconds before retrying block {current_block}...")
            time.sleep(10)

    print(f"🎉 Training Complete! Model digested {total_trained} historical loans.")

if __name__ == "__main__":
    run_historical_training_pipeline()