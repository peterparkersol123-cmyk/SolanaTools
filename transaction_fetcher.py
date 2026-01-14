"""
Transaction Fetcher Module
Fetches and parses Solana transactions from Helius API
"""
import requests
from datetime import datetime
from typing import List, Dict, Optional

class TransactionFetcher:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = f"https://api.helius.xyz/v0"
        
    def fetch_transactions(self, wallet_address: str, max_transactions: int = 1000) -> List[Dict]:
        """Fetch transactions for a wallet"""
        print(f"Fetching transactions for {wallet_address}...")
        
        all_transactions = []
        before_signature = None
        
        while len(all_transactions) < max_transactions:
            # Fetch batch of signatures
            params = {
                'api-key': self.api_key
            }
            
            if before_signature:
                params['before'] = before_signature
            
            url = f"{self.base_url}/addresses/{wallet_address}/transactions"
            
            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                batch = response.json()
                
                if not batch:
                    break
                
                # Parse transactions
                for tx in batch:
                    parsed_tx = self._parse_transaction(tx, wallet_address)
                    if parsed_tx:
                        all_transactions.append(parsed_tx)
                
                # Get last signature for pagination
                if len(batch) > 0:
                    before_signature = batch[-1].get('signature')
                else:
                    break
                
                print(f"Fetched {len(all_transactions)} transactions...")
                
                if len(batch) < 100:  # Less than full page, we're done
                    break
                    
            except Exception as e:
                print(f"Error fetching transactions: {e}")
                break
        
        print(f"Total transactions fetched: {len(all_transactions)}")
        return all_transactions[:max_transactions]
    
    def _parse_transaction(self, tx: Dict, wallet_address: str) -> Optional[Dict]:
        """Parse a transaction into buy/sell format"""
        try:
            # Get timestamp
            timestamp = tx.get('timestamp', 0)
            date = datetime.fromtimestamp(timestamp)
            
            # Get token transfers
            token_transfers = tx.get('tokenTransfers', [])
            native_transfers = tx.get('nativeTransfers', [])
            
            # Look for swaps (token in/out pairs)
            tokens_in = []
            tokens_out = []
            
            for transfer in token_transfers:
                from_address = transfer.get('fromUserAccount', '')
                to_address = transfer.get('toUserAccount', '')
                amount = transfer.get('tokenAmount', 0)
                mint = transfer.get('mint', '')
                
                # Determine if this is incoming or outgoing
                if to_address == wallet_address:
                    tokens_in.append({
                        'mint': mint,
                        'amount': amount,
                        'symbol': self._get_token_symbol(transfer)
                    })
                elif from_address == wallet_address:
                    tokens_out.append({
                        'mint': mint,
                        'amount': amount,
                        'symbol': self._get_token_symbol(transfer)
                    })
            
            # Check for SOL transfers
            sol_in = 0
            sol_out = 0
            
            for transfer in native_transfers:
                from_address = transfer.get('fromUserAccount', '')
                to_address = transfer.get('toUserAccount', '')
                amount = transfer.get('amount', 0) / 1e9  # Convert lamports to SOL
                
                if to_address == wallet_address:
                    sol_in += amount
                elif from_address == wallet_address:
                    sol_out += amount
            
            # Determine transaction type
            if tokens_in and sol_out > 0:
                # Bought tokens with SOL
                return {
                    'type': 'BUY',
                    'date': date,
                    'signature': tx.get('signature'),
                    'token_bought_mint': tokens_in[0]['mint'],
                    'token_bought_symbol': tokens_in[0]['symbol'],
                    'amount_bought': tokens_in[0]['amount'],
                    'amount_sold': sol_out  # SOL spent
                }
            elif tokens_out and sol_in > 0:
                # Sold tokens for SOL
                return {
                    'type': 'SELL',
                    'date': date,
                    'signature': tx.get('signature'),
                    'token_sold_mint': tokens_out[0]['mint'],
                    'token_sold_symbol': tokens_out[0]['symbol'],
                    'amount_sold': tokens_out[0]['amount'],
                    'amount_bought': sol_in  # SOL received
                }
            
            return None
            
        except Exception as e:
            print(f"Error parsing transaction: {e}")
            return None
    
    def _get_token_symbol(self, transfer: Dict) -> str:
        """Extract token symbol from transfer"""
        # Try to get from tokenInfo
        token_info = transfer.get('tokenInfo', {})
        symbol = token_info.get('symbol', '')
        
        if not symbol:
            # Fallback to mint address
            mint = transfer.get('mint', '')
            symbol = mint[:8] if mint else 'Unknown'
        
        return symbol