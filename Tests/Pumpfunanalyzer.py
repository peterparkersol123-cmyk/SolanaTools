"""
Pump.fun Transaction Structure Analyzer
This script fetches transactions and shows you EXACTLY what fields Helius returns
so we can properly detect Pump.fun transactions
"""
import requests
import json
from datetime import datetime

# CONFIGURATION
WALLET = "4yKnfzcf98jm5z3uHvBXjLa9vFB713jWfnWDcpWZCqpH"
HELIUS_API_KEY = "32c0f32e-9d6c-4658-9982-f0b2f0342b23"  # Replace with your key

def analyze_transactions():
    """Fetch and analyze transaction structure"""
    print("=" * 80)
    print("PUMP.FUN TRANSACTION STRUCTURE ANALYZER")
    print("=" * 80)
    print(f"Wallet: {WALLET}")
    print(f"Fetching transactions...\n")
    
    # Fetch transactions
    url = f"https://api.helius.xyz/v0/addresses/{WALLET}/transactions"
    params = {'api-key': HELIUS_API_KEY, 'limit': 50}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        transactions = response.json()
        
        print(f"✅ Fetched {len(transactions)} transactions\n")
        
        # Analyze each transaction
        pumpfun_count = 0
        
        for i, tx in enumerate(transactions[:20]):  # Analyze first 20
            print("=" * 80)
            print(f"TRANSACTION #{i+1}")
            print("=" * 80)
            
            # Basic info
            signature = tx.get('signature', 'N/A')
            timestamp = tx.get('timestamp')
            date = datetime.fromtimestamp(timestamp) if timestamp else None
            tx_type = tx.get('type', 'N/A')
            description = tx.get('description', 'N/A')
            source = tx.get('source', 'N/A')
            
            print(f"Signature: {signature[:16]}...")
            print(f"Date: {date}")
            print(f"Type: {tx_type}")
            print(f"Description: {description}")
            print(f"Source: {source}")
            
            # Check if this looks like Pump.fun
            is_pumpfun = False
            pumpfun_indicators = []
            
            # Check 1: Type field
            if tx_type and 'PUMP' in str(tx_type).upper():
                is_pumpfun = True
                pumpfun_indicators.append(f"Type contains 'PUMP': {tx_type}")
            
            # Check 2: Description
            if description and ('pump.fun' in description.lower() or 'pumpfun' in description.lower()):
                is_pumpfun = True
                pumpfun_indicators.append(f"Description mentions Pump.fun: {description}")
            
            # Check 3: Source
            if source and ('pump' in source.lower()):
                is_pumpfun = True
                pumpfun_indicators.append(f"Source mentions pump: {source}")
            
            # Check 4: Account data
            account_data = tx.get('accountData', [])
            print(f"\nAccount Data ({len(account_data)} accounts):")
            for j, account in enumerate(account_data[:5]):
                acc_id = account.get('account', 'N/A')
                print(f"  [{j+1}] {acc_id}")
                
                if '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' in acc_id:
                    is_pumpfun = True
                    pumpfun_indicators.append(f"Account is primary Pump.fun program")
                elif 'Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1' in acc_id:
                    is_pumpfun = True
                    pumpfun_indicators.append(f"Account is Pump.fun bonding curve")
            
            # Check 5: Instructions
            instructions = tx.get('instructions', [])
            print(f"\nInstructions ({len(instructions)} instructions):")
            for j, inst in enumerate(instructions[:5]):
                prog_id = inst.get('programId', 'N/A')
                print(f"  [{j+1}] Program: {prog_id}")
                
                if '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' in prog_id:
                    is_pumpfun = True
                    pumpfun_indicators.append(f"Instruction uses Pump.fun program")
                elif 'Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1' in prog_id:
                    is_pumpfun = True
                    pumpfun_indicators.append(f"Instruction uses bonding curve")
            
            # Check 6: Token transfers
            token_transfers = tx.get('tokenTransfers', [])
            print(f"\nToken Transfers ({len(token_transfers)} transfers):")
            for j, transfer in enumerate(token_transfers[:3]):
                from_user = transfer.get('fromUserAccount', 'N/A')
                to_user = transfer.get('toUserAccount', 'N/A')
                mint = transfer.get('mint', 'N/A')
                amount = transfer.get('tokenAmount', 0)
                
                print(f"  [{j+1}] From: {from_user[:16]}...")
                print(f"       To: {to_user[:16]}...")
                print(f"       Token: {mint[:16]}...")
                print(f"       Amount: {amount}")
                
                # Check for pump.fun in addresses
                if 'pump' in from_user.lower() or 'pump' in to_user.lower():
                    is_pumpfun = True
                    pumpfun_indicators.append(f"Transfer involves 'pump' address")
            
            # Check 7: Native (SOL) transfers
            native_transfers = tx.get('nativeTransfers', [])
            print(f"\nNative Transfers ({len(native_transfers)} SOL transfers):")
            for j, transfer in enumerate(native_transfers[:3]):
                from_user = transfer.get('fromUserAccount', 'N/A')
                to_user = transfer.get('toUserAccount', 'N/A')
                amount_lamports = transfer.get('amount', 0)
                amount_sol = amount_lamports / 1_000_000_000
                
                print(f"  [{j+1}] From: {from_user[:16]}...")
                print(f"       To: {to_user[:16]}...")
                print(f"       Amount: {amount_sol:.6f} SOL")
            
            # Check 8: Inner instructions
            inner_instructions = tx.get('innerInstructions', [])
            if inner_instructions:
                print(f"\nInner Instructions ({len(inner_instructions)} groups):")
                for j, inner_group in enumerate(inner_instructions[:2]):
                    inner_insts = inner_group.get('instructions', [])
                    print(f"  Group [{j+1}]: {len(inner_insts)} instructions")
                    for k, inst in enumerate(inner_insts[:3]):
                        prog_id = inst.get('programId', 'N/A')
                        print(f"    [{k+1}] {prog_id}")
                        
                        if '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' in prog_id:
                            is_pumpfun = True
                            pumpfun_indicators.append(f"Inner instruction uses Pump.fun")
            
            # Result
            print(f"\n{'🎯 PUMP.FUN DETECTED' if is_pumpfun else '❌ NOT PUMP.FUN'}")
            if pumpfun_indicators:
                print("\nDetection reasons:")
                for indicator in pumpfun_indicators:
                    print(f"  ✓ {indicator}")
            
            if is_pumpfun:
                pumpfun_count += 1
            
            print("\n")
            
            # Stop after finding 5 Pump.fun transactions
            if pumpfun_count >= 5:
                print("Found 5 Pump.fun transactions, stopping analysis...")
                break
        
        # Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total transactions analyzed: {min(20, len(transactions))}")
        print(f"Pump.fun transactions found: {pumpfun_count}")
        
        # Show raw JSON of first Pump.fun transaction
        print("\n" + "=" * 80)
        print("RAW JSON OF FIRST TRANSACTIONcl (for debugging)")
        print("=" * 80)
        print(json.dumps(transactions[0], indent=2)[:3000])
        print("\n... (truncated)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_transactions()