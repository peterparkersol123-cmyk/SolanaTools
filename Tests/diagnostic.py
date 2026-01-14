"""
Test script to verify metadata fetching from multiple sources
"""
import requests
import json

mint = 'GYRxXJ9WzGAhQA4pFLUHjiXP462fWre5NDgdBD2Apump'

print("="*80)
print(f"Testing metadata sources for: {mint[:16]}...")
print("="*80)

# Test 1: DexScreener (most reliable for memecoins)
print("\n1. Testing DexScreener API...")
try:
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    response = requests.get(url, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        
        if data.get('pairs') and len(data['pairs']) > 0:
            pair = data['pairs'][0]
            base_token = pair.get('baseToken', {})
            
            symbol = base_token.get('symbol', '')
            name = base_token.get('name', '')
            logo = pair.get('info', {}).get('imageUrl', '')
            
            print(f"✅ DexScreener SUCCESS!")
            print(f"   Symbol: {symbol}")
            print(f"   Name: {name}")
            print(f"   Logo: {logo[:60]}...")
        else:
            print(f"❌ No pairs found")
    else:
        print(f"❌ API Error: {response.status_code}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Jupiter Token List
print("\n2. Testing Jupiter Token List...")
try:
    url = "https://token.jup.ag/strict"
    response = requests.get(url, timeout=10)
    
    if response.status_code == 200:
        tokens = response.json()
        found = False
        
        for token in tokens:
            if token.get('address', '').lower() == mint.lower():
                found = True
                print(f"✅ Jupiter SUCCESS!")
                print(f"   Symbol: {token.get('symbol', '')}")
                print(f"   Name: {token.get('name', '')}")
                print(f"   Logo: {token.get('logoURI', '')[:60]}...")
                break
        
        if not found:
            print(f"❌ Token not in Jupiter list")
    else:
        print(f"❌ API Error: {response.status_code}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: Helius (we know this returns N/A)
print("\n3. Testing Helius API...")
print("❌ Already confirmed returns N/A")

print("\n" + "="*80)
print("RECOMMENDATION: Use DexScreener as primary source for Pump.fun tokens")
print("="*80)