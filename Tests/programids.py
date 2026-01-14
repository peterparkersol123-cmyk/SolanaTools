"""
Script to discover ALL Pump.fun program IDs used in your wallet transactions
This will help identify if there are additional program IDs beyond the known ones
"""
import requests
import time
from collections import defaultdict

# CONFIGURATION
WALLET_ADDRESS = '4yKnfzcf98jm5z3uHvBXjLa9vFB713jWfnWDcpWZCqpH'
HELIUS_API_KEY = '32c0f32e-9d6c-4658-9982-f0b2f0342b23'
MAX_PAGES = 10  # Fetch 10 pages = ~1000 transactions

# Known Pump.fun program ID from search results
PRIMARY_PUMPFUN_PROGRAM = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'

def fetch_transactions(wallet, api_key, max_pages):
    """Fetch transactions from Helius"""
    print(f"Fetching transactions for: {wallet[:12]}...")
    all_txs = []
    before = None
    
    for page in range(max_pages):
        url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions"
        params = {'api-key': api_key}
        if before:
            params['before'] = before
        
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code != 200:
                print(f"Error: {response.status_code}")
                break
            
            data = response.json()
            if not data:
                break
            
            all_txs.extend(data)
            print(f"Page {page + 1}: {len(data)} txs (Total: {len(all_txs)})")
            
            if len(data) < 100:
                break
            
            before = data[-1].get('signature')
            time.sleep(0.3)
        except Exception as e:
            print(f"Error: {e}")
            break
    
    print(f"\nTotal fetched: {len(all_txs)} transactions\n")
    return all_txs

def analyze_program_ids(transactions):
    """Analyze all program IDs and identify Pump.fun related ones"""
    
    print("="*80)
    print("ANALYZING PROGRAM IDs IN YOUR WALLET TRANSACTIONS")
    print("="*80)
    
    # Track all programs
    program_usage = defaultdict(int)
    program_first_seen = {}
    program_last_seen = {}
    
    # Track which programs appear in same transactions as known Pump.fun
    cooccurrence = defaultdict(int)
    
    for tx in transactions:
        programs_in_tx = set()
        
        # Collect all programs from accountData
        for account in tx.get('accountData', []):
            prog = account.get('account', '')
            if prog:
                programs_in_tx.add(prog)
                program_usage[prog] += 1
                
                # Track first/last seen
                timestamp = tx.get('timestamp', 0)
                if prog not in program_first_seen:
                    program_first_seen[prog] = timestamp
                program_last_seen[prog] = timestamp
        
        # Collect from instructions
        for inst in tx.get('instructions', []):
            prog = inst.get('programId', '')
            if prog:
                programs_in_tx.add(prog)
                program_usage[prog] += 1
                
                timestamp = tx.get('timestamp', 0)
                if prog not in program_first_seen:
                    program_first_seen[prog] = timestamp
                program_last_seen[prog] = timestamp
        
        # Track co-occurrence with known Pump.fun program
        if PRIMARY_PUMPFUN_PROGRAM in programs_in_tx:
            for prog in programs_in_tx:
                if prog != PRIMARY_PUMPFUN_PROGRAM:
                    cooccurrence[prog] += 1
    
    # Sort by usage
    sorted_programs = sorted(program_usage.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\nFound {len(sorted_programs)} unique programs")
    print(f"\nTop 30 most frequently used programs:\n")
    print(f"{'Rank':<6} {'Count':<8} {'Program ID':<50} {'Notes'}")
    print("-" * 100)
    
    for i, (prog, count) in enumerate(sorted_programs[:30], 1):
        notes = []
        
        # Check if it's the known Pump.fun program
        if prog == PRIMARY_PUMPFUN_PROGRAM:
            notes.append("✅ KNOWN PUMP.FUN")
        
        # Check if it appears with Pump.fun frequently
        if prog in cooccurrence and cooccurrence[prog] > 10:
            notes.append(f"Co-occurs with Pump.fun {cooccurrence[prog]}x")
        
        # Check for pump/Pump in name
        if any(keyword in prog for keyword in ['pump', 'Pump', 'PUMP']):
            notes.append("⚠️ 'PUMP' in ID")
        
        note_str = " | ".join(notes) if notes else ""
        print(f"{i:<6} {count:<8} {prog:<50} {note_str}")
    
    # Find potential Pump.fun related programs
    print("\n" + "="*80)
    print("POTENTIAL PUMP.FUN RELATED PROGRAMS")
    print("="*80)
    
    pump_related = []
    
    # 1. The known program
    if PRIMARY_PUMPFUN_PROGRAM in program_usage:
        pump_related.append({
            'program': PRIMARY_PUMPFUN_PROGRAM,
            'count': program_usage[PRIMARY_PUMPFUN_PROGRAM],
            'reason': 'Known Pump.fun program (primary)'
        })
    
    # 2. Programs with 'pump' in the ID
    for prog in program_usage:
        if prog != PRIMARY_PUMPFUN_PROGRAM and any(kw in prog for kw in ['pump', 'Pump', 'PUMP']):
            pump_related.append({
                'program': prog,
                'count': program_usage[prog],
                'reason': 'Contains "pump" in program ID'
            })
    
    # 3. Programs that frequently co-occur with known Pump.fun
    for prog, co_count in cooccurrence.items():
        if co_count >= 20 and prog not in [p['program'] for p in pump_related]:
            # Only include if it's used frequently
            if program_usage[prog] >= 10:
                pump_related.append({
                    'program': prog,
                    'count': program_usage[prog],
                    'reason': f'Co-occurs with Pump.fun in {co_count} transactions'
                })
    
    if pump_related:
        print(f"\nFound {len(pump_related)} potential Pump.fun related programs:\n")
        for item in pump_related:
            print(f"Program: {item['program']}")
            print(f"  Used in: {item['count']} transactions")
            print(f"  Reason: {item['reason']}")
            print()
    else:
        print("\n❌ No Pump.fun programs found in your transactions!")
        print("This could mean:")
        print("  1. No Pump.fun activity in fetched transactions")
        print("  2. Activity is older than fetched range")
        print("  3. The known program ID is incorrect/outdated")
    
    # Generate Python list for copy-paste
    print("\n" + "="*80)
    print("SUGGESTED PROGRAM IDs FOR YOUR CODE")
    print("="*80)
    
    program_list = [item['program'] for item in pump_related]
    
    if program_list:
        print("\nPUMPFUN_PROGRAMS = [")
        for prog in program_list:
            print(f"    '{prog}',")
        print("]")
    else:
        print("\n# No Pump.fun programs detected")
        print("# Using documented primary program:")
        print("PUMPFUN_PROGRAMS = [")
        print(f"    '{PRIMARY_PUMPFUN_PROGRAM}',")
        print("]")
    
    # Additional verification check
    print("\n" + "="*80)
    print("VERIFICATION: Check these on Solscan")
    print("="*80)
    print("\nVerify any suspicious programs at:")
    for prog in program_list[:5]:  # Top 5
        print(f"https://solscan.io/account/{prog}")
    
    return program_list

def main():
    print("PUMP.FUN PROGRAM ID DISCOVERY TOOL")
    print("="*80)
    print(f"Wallet: {WALLET_ADDRESS}")
    print(f"Will fetch up to {MAX_PAGES} pages (~{MAX_PAGES * 100} transactions)")
    print("="*80 + "\n")
    
    # Fetch transactions
    transactions = fetch_transactions(WALLET_ADDRESS, HELIUS_API_KEY, MAX_PAGES)
    
    if not transactions:
        print("❌ No transactions fetched!")
        return
    
    # Analyze
    program_ids = analyze_program_ids(transactions)
    
    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)
    print("\n1. Copy the PUMPFUN_PROGRAMS list above")
    print("2. Replace the existing list in your tax calculator")
    print("3. Re-run the tax calculator")
    print("4. Verify any unknown programs on Solscan before using")
    print("\n" + "="*80)

if __name__ == "__main__":
    main()