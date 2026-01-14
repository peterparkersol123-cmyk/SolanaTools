"""
Solana Memecoin Tax Calculator - FIXED WITH NATIVE BALANCE CHANGE
Key fixes:
1. Use nativeBalanceChange for accurate net SOL amounts (matches GMGN/Cielo)
2. Proper wrapped SOL handling
3. Simplified swap creation logic
4. Better token-to-token swap handling
"""
import requests
import time
import asyncio
import aiohttp
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Optional
import json
import os

# CONSTANTS
LAMPORTS_PER_SOL = 1_000_000_000
MAX_TRANSACTIONS = 1000
# Helius API rate limits:
# Free tier: 10 req/sec (0.1s delay)
# Paid tier: 50 req/sec (0.02s delay)
API_RATE_LIMIT_DELAY = 0.02  # Updated for paid tier (50 req/sec)
COINGECKO_DELAY = 0.1
FLOAT_EPSILON = 0.0001
DEFAULT_SOL_PRICE_USD = 150.0
SOL_MINT_ADDRESS = 'So11111111111111111111111111111111111111112'
WSOL_MINT_ADDRESS = 'So11111111111111111111111111111111111111112'

class SolanaMemecoinTaxCalculator:
    def __init__(self, wallet_address: str, helius_api_key: str, accounting_method: str = "FIFO", days_back: Optional[int] = None):
        self.wallet_address = wallet_address
        self.helius_api_key = helius_api_key
        self.accounting_method = accounting_method.upper()
        self.days_back = days_back
        self.transactions = []
        self.holdings = defaultdict(list)
        self.taxable_events = []
        
        self.token_metadata = {}
        self.symbol_to_mint = {'SOL': SOL_MINT_ADDRESS}
        self.sol_price_cache = {}
        
        self.token_stats = defaultdict(lambda: {
            'total_bought': 0.0,
            'total_sold': 0.0,
            'total_cost': 0.0,
            'total_proceeds': 0.0,
            'first_purchase_date': None,
            'last_sale_date': None,
            'total_trades': 0
        })
        
        self.sol_deposits = []
        self.sol_withdrawals = []
        self.sol_spent_trading = 0.0
        self.sol_received_trading = 0.0
        
    def fetch_wallet_transactions(self, progress_callback=None) -> List[Dict]:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self._fetch_and_parse_async(progress_callback))
    
    async def _fetch_and_parse_async(self, progress_callback=None) -> List[Dict]:
        print(f"Fetching transactions for {self.wallet_address} (async mode)...")
        
        tx_queue = asyncio.Queue()
        parsed_swaps = []
        fetch_complete = asyncio.Event()
        processing_complete = asyncio.Event()
        
        processing_task = asyncio.create_task(
            self._process_transactions_async(tx_queue, parsed_swaps, fetch_complete, processing_complete, progress_callback)
        )
        
        fetching_task = asyncio.create_task(
            self._fetch_transactions_async(tx_queue, fetch_complete, progress_callback)
        )
        
        await asyncio.gather(fetching_task, processing_task)
        
        print(f"\nTotal transactions processed: {len(parsed_swaps)}")
        return parsed_swaps
    
    async def _fetch_transactions_async(self, tx_queue: asyncio.Queue, fetch_complete: asyncio.Event, progress_callback=None):
        async with aiohttp.ClientSession() as session:
            before_signature = None
            page = 0
            total_fetched = 0
            
            while True:
                url = f"https://api.helius.xyz/v0/addresses/{self.wallet_address}/transactions"
                params = {'api-key': self.helius_api_key}
                
                if before_signature:
                    params['before'] = before_signature
                
                try:
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status != 200:
                            print(f"API Error: {response.status}")
                            break
                        
                        data = await response.json()
                        
                        if not data:
                            break
                        
                        for tx in data:
                            await tx_queue.put(tx)
                            total_fetched += 1
                        
                        page += 1
                        
                        if progress_callback:
                            progress_callback({
                                'type': 'fetch_progress',
                                'message': f'Fetched page {page}: {len(data)} transactions (Total: {total_fetched})',
                                'data': {'page': page, 'transactions_on_page': len(data), 'total_transactions': total_fetched}
                            })
                        
                        if total_fetched >= MAX_TRANSACTIONS:
                            print(f"Reached limit of {MAX_TRANSACTIONS} transactions")
                            break
                        
                        print(f"Page {page}: {len(data)} transactions (Total: {total_fetched})")
                        
                        if len(data) < 100:
                            break
                            
                        before_signature = data[-1].get('signature')
                        await asyncio.sleep(API_RATE_LIMIT_DELAY)
                        
                except Exception as e:
                    print(f"Error fetching transactions: {e}")
                    break
            
            fetch_complete.set()
            print(f"Fetching complete: {total_fetched} transactions")
    
    async def _process_transactions_async(self, tx_queue: asyncio.Queue, parsed_swaps: List[Dict], 
                                         fetch_complete: asyncio.Event, processing_complete: asyncio.Event,
                                         progress_callback=None):
        PUMPFUN_PROGRAMS = [
            '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P',
            'Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1',
            '62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV',
            '4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf',
            '8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt',
        ]
        
        cutoff_date = None
        if self.days_back:
            cutoff_date = datetime.now() - timedelta(days=self.days_back)
        
        processed_count = 0
        
        while True:
            if fetch_complete.is_set() and tx_queue.empty():
                break
            
            try:
                try:
                    tx = await asyncio.wait_for(tx_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if fetch_complete.is_set():
                        break
                    continue
                
                swaps = await asyncio.to_thread(self._parse_single_transaction, tx, PUMPFUN_PROGRAMS, cutoff_date)
                
                if swaps:
                    parsed_swaps.extend(swaps)
                    processed_count += len(swaps)
                    
                    if processed_count % 50 == 0 and progress_callback:
                        pumpfun_count = sum(1 for s in parsed_swaps if s.get('is_pumpfun', False))
                        progress_callback({
                            'type': 'parse_progress',
                            'message': f'Processed {processed_count} swaps ({pumpfun_count} Pump.fun)...',
                            'data': {'parsed_swaps': processed_count, 'pumpfun': pumpfun_count}
                        })
                
            except Exception as e:
                print(f"Error processing transaction: {e}")
                continue
        
        pumpfun_count = sum(1 for s in parsed_swaps if s.get('is_pumpfun', False))
        print(f"Parsed {len(parsed_swaps)} swaps ({pumpfun_count} Pump.fun, {len(parsed_swaps) - pumpfun_count} other)")
        processing_complete.set()
    
    def _parse_single_transaction(self, tx: Dict, pumpfun_programs: List[str], cutoff_date: Optional[datetime]) -> List[Dict]:
        """
        FIXED: Parse transaction using nativeBalanceChange for accurate net SOL amounts
        This matches GMGN/Cielo by using the actual net change in wallet balance
        """
        swaps = []
        
        try:
            timestamp = tx.get('timestamp')
            if not timestamp:
                return swaps
            
            date = datetime.fromtimestamp(timestamp)
            
            if cutoff_date and date < cutoff_date:
                return swaps
            
            # Detect Pump.fun
            is_pumpfun = False
            source = tx.get('source', '')
            if source == 'PUMP_AMM' or 'PUMP' in source.upper():
                is_pumpfun = True
            
            if not is_pumpfun:
                account_data = tx.get('accountData', [])
                for account in account_data:
                    if account.get('account', '') in pumpfun_programs:
                        is_pumpfun = True
                        break
            
            wallet_lower = self.wallet_address.lower()
            
            # CRITICAL FIX: Get NET SOL balance change from account data
            # This is what GMGN uses - it's the actual net change after all fees
            net_sol_change = 0.0
            for account in tx.get('accountData', []):
                if account.get('account', '').lower() == wallet_lower:
                    net_sol_change = account.get('nativeBalanceChange', 0) / LAMPORTS_PER_SOL
                    break
            
            # Parse token transfers
            token_transfers = tx.get('tokenTransfers', [])
            if not token_transfers:
                # Pure SOL deposit or withdrawal
                if abs(net_sol_change) > FLOAT_EPSILON:
                    if net_sol_change > 0:
                        self.sol_deposits.append({
                            'date': date,
                            'amount': net_sol_change,
                            'signature': tx.get('signature', '')
                        })
                    else:
                        self.sol_withdrawals.append({
                            'date': date,
                            'amount': abs(net_sol_change),
                            'signature': tx.get('signature', '')
                        })
                return swaps
            
            # Separate token movements and combine same tokens
            tokens_in_dict = {}
            tokens_out_dict = {}
            
            for transfer in token_transfers:
                mint = transfer.get('mint', '')
                from_addr = transfer.get('fromUserAccount', '').lower()
                to_addr = transfer.get('toUserAccount', '').lower()
                amount = float(transfer.get('tokenAmount', 0))
                
                # Skip wrapped SOL in token transfers - we use nativeBalanceChange instead
                if mint == SOL_MINT_ADDRESS or mint == WSOL_MINT_ADDRESS:
                    continue
                
                if to_addr == wallet_lower:
                    # Combine multiple transfers of same token
                    tokens_in_dict[mint] = tokens_in_dict.get(mint, 0) + amount
                elif from_addr == wallet_lower:
                    tokens_out_dict[mint] = tokens_out_dict.get(mint, 0) + amount
            
            # Convert to list format
            tokens_in = [{'mint': mint, 'amount': amt} for mint, amt in tokens_in_dict.items()]
            tokens_out = [{'mint': mint, 'amount': amt} for mint, amt in tokens_out_dict.items()]
            
            # Create swaps based on net SOL change and token movements
            # CRITICAL: Only track sol_spent/received ONCE per transaction, not per token
            
            # Case 1: BUY - SOL decreased, tokens increased
            if net_sol_change < -FLOAT_EPSILON and tokens_in and not tokens_out:
                sol_spent = abs(net_sol_change)
                
                # If multiple tokens bought in one transaction, split SOL proportionally
                # Or create separate swaps but don't count SOL multiple times
                if len(tokens_in) == 1:
                    # Simple case: one token bought
                    self.sol_spent_trading += sol_spent
                    swaps.append({
                        'date': date,
                        'type': 'BUY',
                        'token_sold_mint': SOL_MINT_ADDRESS,
                        'token_sold_symbol': 'SOL',
                        'amount_sold': sol_spent,
                        'token_bought_mint': tokens_in[0]['mint'],
                        'amount_bought': tokens_in[0]['amount'],
                        'signature': tx.get('signature', ''),
                        'is_pumpfun': is_pumpfun
                    })
                else:
                    # Multiple tokens - split SOL proportionally (equal split as approximation)
                    self.sol_spent_trading += sol_spent
                    sol_per_token = sol_spent / len(tokens_in)
                    
                    for token_in in tokens_in:
                        swaps.append({
                            'date': date,
                            'type': 'BUY',
                            'token_sold_mint': SOL_MINT_ADDRESS,
                            'token_sold_symbol': 'SOL',
                            'amount_sold': sol_per_token,
                            'token_bought_mint': token_in['mint'],
                            'amount_bought': token_in['amount'],
                            'signature': tx.get('signature', ''),
                            'is_pumpfun': is_pumpfun
                        })
            
            # Case 2: SELL - tokens decreased, SOL increased
            elif net_sol_change > FLOAT_EPSILON and tokens_out and not tokens_in:
                sol_received = net_sol_change
                
                # If multiple tokens sold in one transaction, split SOL proportionally
                if len(tokens_out) == 1:
                    # Simple case: one token sold
                    self.sol_received_trading += sol_received
                    swaps.append({
                        'date': date,
                        'type': 'SELL',
                        'token_sold_mint': tokens_out[0]['mint'],
                        'amount_sold': tokens_out[0]['amount'],
                        'token_bought_mint': SOL_MINT_ADDRESS,
                        'token_bought_symbol': 'SOL',
                        'amount_bought': sol_received,
                        'signature': tx.get('signature', ''),
                        'is_pumpfun': is_pumpfun
                    })
                else:
                    # Multiple tokens - split SOL proportionally
                    self.sol_received_trading += sol_received
                    sol_per_token = sol_received / len(tokens_out)
                    
                    for token_out in tokens_out:
                        swaps.append({
                            'date': date,
                            'type': 'SELL',
                            'token_sold_mint': token_out['mint'],
                            'amount_sold': token_out['amount'],
                            'token_bought_mint': SOL_MINT_ADDRESS,
                            'token_bought_symbol': 'SOL',
                            'amount_bought': sol_per_token,
                            'signature': tx.get('signature', ''),
                            'is_pumpfun': is_pumpfun
                        })
            
            # Case 3: Token-to-token swap
            elif tokens_out and tokens_in:
                for token_out in tokens_out:
                    for token_in in tokens_in:
                        if token_out['mint'] != token_in['mint']:
                            swaps.append({
                                'date': date,
                                'type': 'SWAP',
                                'token_sold_mint': token_out['mint'],
                                'amount_sold': token_out['amount'],
                                'token_bought_mint': token_in['mint'],
                                'amount_bought': token_in['amount'],
                                'sol_change': net_sol_change,  # Track any SOL involved
                                'signature': tx.get('signature', ''),
                                'is_pumpfun': is_pumpfun
                            })
        
        except Exception as e:
            print(f"Error parsing transaction: {e}")
            import traceback
            traceback.print_exc()
        
        return swaps
    
    def _get_token_metadata(self, mint: str) -> Dict:
        if mint == SOL_MINT_ADDRESS or mint == 'SOL':
            return {
                'symbol': 'SOL',
                'name': 'Solana',
                'logoURI': 'https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/So11111111111111111111111111111111111111112/logo.png',
                'mint': SOL_MINT_ADDRESS
            }
        
        if mint in self.token_metadata:
            return self.token_metadata[mint]
        
        try:
            url = f"https://api.helius.xyz/v0/token-metadata"
            response = requests.post(url, params={'api-key': self.helius_api_key}, 
                                   json={'mintAccounts': [mint]}, timeout=10)
            metadata_list = response.json()
            
            if metadata_list:
                meta = metadata_list[0]
                symbol = meta.get('symbol', mint[:8])
                name = meta.get('name', symbol)
                logo = meta.get('logoURI') or meta.get('image') or ''
                
                result = {'symbol': symbol, 'name': name, 'logoURI': logo, 'mint': mint}
                self.token_metadata[mint] = result
                return result
        except:
            pass
        
        fallback = {'symbol': mint[:8], 'name': mint[:8], 'logoURI': '', 'mint': mint}
        self.token_metadata[mint] = fallback
        return fallback
    
    def _get_token_symbol(self, mint: str) -> str:
        return self._get_token_metadata(mint)['symbol']
    
    def _get_sol_price_usd(self, date: datetime) -> float:
        date_key = date.strftime("%Y-%m-%d")
        
        if date_key in self.sol_price_cache:
            return self.sol_price_cache[date_key]
        
        try:
            date_str = date.strftime("%d-%m-%Y")
            url = f"https://api.coingecko.com/api/v3/coins/solana/history"
            response = requests.get(url, params={'date': date_str, 'localization': 'false'}, timeout=10)
            data = response.json()
            
            if 'market_data' in data:
                price = data['market_data']['current_price'].get('usd', DEFAULT_SOL_PRICE_USD)
                self.sol_price_cache[date_key] = price
                return price
        except Exception as e:
            print(f"SOL price fetch error for {date_key}: {e}")
        
        self.sol_price_cache[date_key] = DEFAULT_SOL_PRICE_USD
        return DEFAULT_SOL_PRICE_USD
    
    def calculate_taxes_from_wallet(self, progress_callback=None, debug_token_mint=None):
        """Main calculation with nativeBalanceChange for accurate USD values"""
        if progress_callback:
            progress_callback({'type': 'status', 'message': 'Fetching transactions...', 'data': {}})
        
        swaps = self.fetch_wallet_transactions(progress_callback)
        
        if not swaps:
            if progress_callback:
                progress_callback({'type': 'error', 'message': 'No swaps found', 'data': {}})
            return None
        
        if progress_callback:
            progress_callback({'type': 'status', 'message': f'Processing {len(swaps)} swaps...', 'data': {}})
        
        print("\nCalculating taxes...")
        
        # Debug: filter and show swaps for target token
        if debug_token_mint:
            debug_swaps = [s for s in swaps if s.get('token_sold_mint') == debug_token_mint or s.get('token_bought_mint') == debug_token_mint]
            print(f"\n{'='*80}")
            print(f"DEBUG: Found {len(debug_swaps)} swaps involving {debug_token_mint[:8]}...")
            print(f"{'='*80}")
        
        for i, swap in enumerate(swaps):
            try:
                if (i + 1) % 1 == 0:
                    if progress_callback:
                        progress_callback({
                            'type': 'progress',
                            'message': f"Processed {i + 1}/{len(swaps)}",
                            'data': {'processed': i + 1, 'total': len(swaps)}
                        })
                
                # Get token info
                token_sold_mint = swap['token_sold_mint']
                token_bought_mint = swap['token_bought_mint']
                
                token_sold_symbol = swap.get('token_sold_symbol') or self._get_token_symbol(token_sold_mint)
                token_bought_symbol = swap.get('token_bought_symbol') or self._get_token_symbol(token_bought_mint)
                
                self.symbol_to_mint[token_sold_symbol] = token_sold_mint
                self.symbol_to_mint[token_bought_symbol] = token_bought_mint
                
                amount_sold = swap['amount_sold']
                amount_bought = swap['amount_bought']
                
                sol_price = self._get_sol_price_usd(swap['date'])
                
                # DEBUG: Print details for target token
                is_debug_token = debug_token_mint and (token_sold_mint == debug_token_mint or token_bought_mint == debug_token_mint)
                
                # FIXED: USD calculation using nativeBalanceChange logic
                # The amounts in the swap already represent the NET amounts
                
                if token_sold_symbol == 'SOL':
                    # Buying tokens with SOL
                    usd_value = amount_sold * sol_price
                    usd_sold = usd_value
                    usd_bought = usd_value
                    
                    if is_debug_token:
                        print(f"\n{'─'*80}")
                        print(f"BUY #{i+1} - {swap['date'].strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  Type: Buying {token_bought_symbol}")
                        print(f"  SOL Spent: {amount_sold:.4f} SOL")
                        print(f"  SOL Price: ${sol_price:.2f}")
                        print(f"  USD Value: ${usd_value:.2f}")
                        print(f"  Tokens Bought: {amount_bought:,.0f}")
                        print(f"  Signature: {swap.get('signature', '')[:16]}...")
                        
                elif token_bought_symbol == 'SOL':
                    # Selling tokens for SOL
                    usd_value = amount_bought * sol_price
                    usd_sold = usd_value
                    usd_bought = usd_value
                    
                    if is_debug_token:
                        print(f"\n{'─'*80}")
                        print(f"SELL #{i+1} - {swap['date'].strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  Type: Selling {token_sold_symbol}")
                        print(f"  SOL Received: {amount_bought:.4f} SOL")
                        print(f"  SOL Price: ${sol_price:.2f}")
                        print(f"  USD Value: ${usd_value:.2f}")
                        print(f"  Tokens Sold: {amount_sold:,.0f}")
                        print(f"  Signature: {swap.get('signature', '')[:16]}...")
                        
                else:
                    # Token-to-token swap - estimate from holdings
                    usd_sold = self._get_cost_basis_estimate(token_sold_symbol, amount_sold)
                    usd_bought = usd_sold
                    
                    if is_debug_token:
                        print(f"\n{'─'*80}")
                        print(f"SWAP #{i+1} - {swap['date'].strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  Type: {token_sold_symbol} → {token_bought_symbol}")
                        print(f"  Estimated USD: ${usd_sold:.2f}")
                
                # Process sale (dispose of token)
                if token_sold_symbol != 'SOL':
                    cost_before = self.token_stats[token_sold_symbol]['total_cost']
                    proceeds_before = self.token_stats[token_sold_symbol]['total_proceeds']
                    
                    self._process_sale(swap['date'], token_sold_symbol, token_sold_mint, amount_sold, usd_sold)
                    
                    if is_debug_token:
                        cost_after = self.token_stats[token_sold_symbol]['total_cost']
                        proceeds_after = self.token_stats[token_sold_symbol]['total_proceeds']
                        print(f"  AFTER SALE:")
                        print(f"    Total Cost: ${cost_before:.2f} → ${cost_after:.2f}")
                        print(f"    Total Proceeds: ${proceeds_before:.2f} → ${proceeds_after:.2f}")
                        print(f"    Running P&L: ${proceeds_after - cost_after:.2f}")
                    self._process_sale(swap['date'], token_sold_symbol, token_sold_mint, amount_sold, usd_sold)
                    
                    if progress_callback and self.taxable_events:
                        latest = self.taxable_events[-1]
                        token_meta = self._get_token_metadata(token_sold_mint)
                        stats = self.token_stats[token_sold_symbol]
                        
                        progress_callback({
                            'type': 'event',
                            'message': f'Sale: {token_sold_symbol}',
                            'data': {
                                'event': {
                                    'date': latest['date'].strftime('%Y-%m-%d %H:%M'),
                                    'token': latest['token'],
                                    'token_mint': latest.get('token_mint', ''),
                                    'amount': round(latest['amount'], 6),
                                    'proceeds': round(latest['proceeds'], 2),
                                    'cost': round(latest['cost_basis'], 2),
                                    'gain': round(latest['capital_gain'], 2),
                                    'total_bought': round(stats['total_bought'], 6),
                                    'total_sold': round(stats['total_sold'], 6),
                                    'total_invested': round(stats['total_cost'], 2),
                                    'total_proceeds': round(stats['total_proceeds'], 2)
                                },
                                'token_metadata': token_meta
                            }
                        })
                
                # Process buy (acquire token)
                if token_bought_symbol != 'SOL':
                    cost_before = self.token_stats[token_bought_symbol]['total_cost']
                    
                    self._process_buy(swap['date'], token_bought_symbol, amount_bought, usd_bought)
                    
                    if is_debug_token and token_bought_mint == debug_token_mint:
                        cost_after = self.token_stats[token_bought_symbol]['total_cost']
                        print(f"  AFTER BUY:")
                        print(f"    Total Cost: ${cost_before:.2f} → ${cost_after:.2f}")
                        print(f"    Total Bought: {self.token_stats[token_bought_symbol]['total_bought']:,.0f} tokens")
                
                time.sleep(COINGECKO_DELAY)
                
            except Exception as e:
                print(f"Error processing swap {i+1}: {e}")
                import traceback
                traceback.print_exc()
        
        if progress_callback:
            progress_callback({'type': 'status', 'message': 'Generating report...', 'data': {}})
        
        # DEBUG: Print final summary for target token
        if debug_token_mint:
            debug_meta = self._get_token_metadata(debug_token_mint)
            debug_symbol = debug_meta['symbol']
            if debug_symbol in self.token_stats:
                stats = self.token_stats[debug_symbol]
                print(f"\n{'='*80}")
                print(f"FINAL SUMMARY FOR {debug_symbol}")
                print(f"{'='*80}")
                print(f"Total Bought: {stats['total_bought']:,.0f} tokens")
                print(f"Total Sold: {stats['total_sold']:,.0f} tokens")
                print(f"Total Cost: ${stats['total_cost']:.2f}")
                print(f"Total Proceeds: ${stats['total_proceeds']:.2f}")
                print(f"Net Gain/Loss: ${stats['total_proceeds'] - stats['total_cost']:.2f}")
                print(f"Total Trades: {stats['total_trades']}")
                print(f"\nExpected (from simple script): $700.64")
                print(f"Expected (from GMGN): $724.31")
                print(f"Difference: ${(stats['total_proceeds'] - stats['total_cost']) - 700.64:+.2f}")
                print(f"{'='*80}\n")
        
        return self
    
    def _get_cost_basis_estimate(self, token: str, amount: float) -> float:
        if token not in self.holdings or not self.holdings[token]:
            return 0.0
        
        total_cost = sum(lot['total_cost_basis'] for lot in self.holdings[token])
        total_amount = sum(lot['amount'] for lot in self.holdings[token])
        
        if total_amount > FLOAT_EPSILON:
            return (total_cost / total_amount) * amount
        return 0.0
    
    def _process_buy(self, date: datetime, token: str, amount: float, cost_usd: float):
        if amount <= FLOAT_EPSILON:
            return
        
        self.holdings[token].append({
            'date': date,
            'amount': amount,
            'cost_basis_per_unit': cost_usd / amount if amount > FLOAT_EPSILON else 0,
            'total_cost_basis': cost_usd
        })
        
        stats = self.token_stats[token]
        stats['total_bought'] += amount
        stats['total_cost'] += cost_usd
        stats['total_trades'] += 1
        if not stats['first_purchase_date'] or date < stats['first_purchase_date']:
            stats['first_purchase_date'] = date
    
    def _process_sale(self, date: datetime, token: str, token_mint: str, amount: float, proceeds: float) -> float:
        if amount <= FLOAT_EPSILON:
            return 0
        
        stats = self.token_stats[token]
        stats['total_sold'] += amount
        stats['total_proceeds'] += proceeds
        stats['total_trades'] += 1
        if not stats['last_sale_date'] or date > stats['last_sale_date']:
            stats['last_sale_date'] = date
        
        if token not in self.holdings or not self.holdings[token]:
            gain = proceeds
            self.taxable_events.append({
                'date': date, 'token': token, 'token_mint': token_mint,
                'amount': amount, 'proceeds': proceeds,
                'cost_basis': 0, 'capital_gain': gain
            })
            return gain
        
        remaining = amount
        total_cost = 0.0
        lots = self.holdings[token] if self.accounting_method == 'FIFO' else list(reversed(self.holdings[token]))
        
        while remaining > FLOAT_EPSILON and lots:
            lot = lots[0]
            from_lot = min(remaining, lot['amount'])
            total_cost += from_lot * lot['cost_basis_per_unit']
            lot['amount'] -= from_lot
            remaining -= from_lot
            
            if lot['amount'] < FLOAT_EPSILON:
                lots.pop(0)
                if self.accounting_method == 'LIFO':
                    self.holdings[token].pop()
        
        gain = proceeds - total_cost
        self.taxable_events.append({
            'date': date, 'token': token, 'token_mint': token_mint,
            'amount': amount, 'proceeds': proceeds,
            'cost_basis': total_cost, 'capital_gain': gain
        })
        return gain
    
    def generate_report(self) -> str:
        """Generate comprehensive text report"""
        total_gains = sum(e['capital_gain'] for e in self.taxable_events)
        total_proceeds = sum(e['proceeds'] for e in self.taxable_events)
        total_cost = sum(e['cost_basis'] for e in self.taxable_events)
        
        gains_by_token = defaultdict(float)
        for e in self.taxable_events:
            gains_by_token[e['token']] += e['capital_gain']
        
        report = []
        report.append("=" * 80)
        report.append("SOLANA MEMECOIN TAX REPORT (FIXED - nativeBalanceChange)")
        report.append(f"Wallet: {self.wallet_address}")
        report.append(f"Method: {self.accounting_method}")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)
        report.append("")
        
        report.append("TAX SUMMARY")
        report.append("-" * 80)
        report.append(f"Total Taxable Sales: {len(self.taxable_events)}")
        report.append(f"Total Proceeds: ${total_proceeds:,.2f}")
        report.append(f"Total Cost Basis: ${total_cost:,.2f}")
        report.append(f"NET CAPITAL GAIN/LOSS: ${total_gains:,.2f}")
        report.append("")
        
        report.append("SOL FLOW ANALYSIS (Using nativeBalanceChange)")
        report.append("-" * 80)
        total_deposits = sum(d['amount'] for d in self.sol_deposits)
        total_withdrawals = sum(w['amount'] for w in self.sol_withdrawals)
        report.append(f"SOL Deposits: {len(self.sol_deposits)} transactions, {total_deposits:.4f} SOL")
        report.append(f"SOL Withdrawals: {len(self.sol_withdrawals)} transactions, {total_withdrawals:.4f} SOL")
        report.append(f"SOL Spent on Trading: {self.sol_spent_trading:.4f} SOL")
        report.append(f"SOL Received from Trading: {self.sol_received_trading:.4f} SOL")
        report.append(f"Net SOL from Trading: {self.sol_received_trading - self.sol_spent_trading:.4f} SOL")
        report.append("")
        
        report.append("TOKEN PERFORMANCE (Top 15 by absolute gain/loss)")
        report.append("-" * 80)
        report.append(f"{'Token':<12} {'Invested':<12} {'Sold For':<12} {'Gain/Loss':<12} {'ROI':<10} {'Trades':<8}")
        report.append("-" * 80)
        
        filtered = [(t, g) for t, g in gains_by_token.items() if t != 'SOL']
        sorted_tokens = sorted(filtered, key=lambda x: abs(x[1]), reverse=True)[:15]
        
        for token, gain in sorted_tokens:
            stats = self.token_stats[token]
            invested = stats['total_cost']
            sold_for = stats['total_proceeds']
            roi = (gain / invested * 100) if invested > 0 else 0
            trades = stats['total_trades']
            
            report.append(f"{token:<12} ${invested:<11,.2f} ${sold_for:<11,.2f} ${gain:<11,.2f} {roi:>8.1f}% {trades:<8}")
        
        return "\n".join(report)
    
    def generate_json_report(self) -> Dict:
        """Generate comprehensive JSON report"""
        total_gains = sum(e['capital_gain'] for e in self.taxable_events)
        total_proceeds = sum(e['proceeds'] for e in self.taxable_events)
        total_cost = sum(e['cost_basis'] for e in self.taxable_events)
        
        gains_by_mint = defaultdict(float)
        for e in self.taxable_events:
            mint = e.get('token_mint', '')
            if mint and mint != SOL_MINT_ADDRESS:
                gains_by_mint[mint] += e['capital_gain']
        
        # Build token list with enhanced stats
        tokens_list = []
        for mint, gain in sorted(gains_by_mint.items(), key=lambda x: abs(x[1]), reverse=True)[:50]:
            meta = self._get_token_metadata(mint)
            symbol = meta['symbol']
            stats = self.token_stats[symbol]
            
            roi = (gain / stats['total_cost'] * 100) if stats['total_cost'] > 0 else 0
            current_holdings = sum(lot['amount'] for lot in self.holdings.get(symbol, []))
            
            total_bought_tokens = stats['total_bought']
            total_sold_tokens = stats['total_sold']
            
            avg_buy_price = (stats['total_cost'] / total_bought_tokens) if total_bought_tokens > 0 else 0
            avg_sell_price = (stats['total_proceeds'] / total_sold_tokens) if total_sold_tokens > 0 else 0
            
            tokens_list.append({
                'symbol': symbol,
                'name': meta['name'],
                'logoURI': meta['logoURI'],
                'mint': mint,
                'gain': round(gain, 2),
                'invested': round(stats['total_cost'], 2),
                'sold_for': round(stats['total_proceeds'], 2),
                'roi_percent': round(roi, 1),
                'total_trades': stats['total_trades'],
                'total_bought': round(total_bought_tokens, 2),
                'total_sold': round(total_sold_tokens, 2),
                'current_holdings': round(current_holdings, 2),
                'avg_buy_price': round(avg_buy_price, 6),
                'avg_sell_price': round(avg_sell_price, 6),
                'first_purchase': stats['first_purchase_date'].strftime('%Y-%m-%d') if stats['first_purchase_date'] else None,
                'last_sale': stats['last_sale_date'].strftime('%Y-%m-%d') if stats['last_sale_date'] else None
            })
        
        # SOL flow data
        total_sol_deposits = sum(d['amount'] for d in self.sol_deposits)
        total_sol_withdrawals = sum(w['amount'] for w in self.sol_withdrawals)
        
        sol_flow = {
            'deposits': {
                'count': len(self.sol_deposits),
                'total_sol': round(total_sol_deposits, 4),
                'transactions': [
                    {
                        'date': d['date'].strftime('%Y-%m-%d %H:%M'),
                        'amount': round(d['amount'], 4),
                        'signature': d['signature']
                    } for d in sorted(self.sol_deposits, key=lambda x: x['date'], reverse=True)[:20]
                ]
            },
            'withdrawals': {
                'count': len(self.sol_withdrawals),
                'total_sol': round(total_sol_withdrawals, 4),
                'transactions': [
                    {
                        'date': w['date'].strftime('%Y-%m-%d %H:%M'),
                        'amount': round(w['amount'], 4),
                        'signature': w['signature']
                    } for w in sorted(self.sol_withdrawals, key=lambda x: x['date'], reverse=True)[:20]
                ]
            },
            'trading': {
                'sol_spent': round(self.sol_spent_trading, 4),
                'sol_received': round(self.sol_received_trading, 4),
                'net_sol': round(self.sol_received_trading - self.sol_spent_trading, 4)
            }
        }
        
        # Events list
        events_list = []
        for e in sorted(self.taxable_events, key=lambda x: x['date'], reverse=True)[:50]:
            events_list.append({
                'date': e['date'].strftime('%Y-%m-%d %H:%M'),
                'token': e['token'],
                'token_mint': e.get('token_mint', ''),
                'amount': round(e['amount'], 6),
                'proceeds': round(e['proceeds'], 2),
                'cost': round(e['cost_basis'], 2),
                'gain': round(e['capital_gain'], 2)
            })
        
        # Portfolio statistics
        winning_trades = sum(1 for e in self.taxable_events if e['capital_gain'] > 0)
        losing_trades = sum(1 for e in self.taxable_events if e['capital_gain'] < 0)
        win_rate = (winning_trades / len(self.taxable_events) * 100) if self.taxable_events else 0
        
        avg_gain_per_trade = total_gains / len(self.taxable_events) if self.taxable_events else 0
        
        return {
            'wallet': self.wallet_address,
            'accounting_method': self.accounting_method,
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_proceeds': round(total_proceeds, 2),
                'total_cost': round(total_cost, 2),
                'net_gain': round(total_gains, 2),
                'taxable_sales': len(self.taxable_events),
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate_percent': round(win_rate, 1),
                'avg_gain_per_trade': round(avg_gain_per_trade, 2)
            },
            'sol_flow': sol_flow,
            'tokens': tokens_list,
            'events': events_list
        }


if __name__ == "__main__":
    print("Solana Memecoin Tax Calculator (FIXED - nativeBalanceChange)")
    print("=" * 80)
    
    API_KEY = os.environ.get('HELIUS_API_KEY', '32c0f32e-9d6c-4658-9982-f0b2f0342b23')
    WALLET = os.environ.get('WALLET_ADDRESS', '4yKnfzcf98jm5z3uHvBXjLa9vFB713jWfnWDcpWZCqpH')
    DEBUG_TOKEN = 'GYRxXJ9WzGAhQA4pFLUHjiXP462fWre5NDgdBD2Apump'  # The token we're debugging
    
    calc = SolanaMemecoinTaxCalculator(WALLET, API_KEY, "FIFO")
    result = calc.calculate_taxes_from_wallet(debug_token_mint=DEBUG_TOKEN)
    
    if result:
        print("\n" + calc.generate_report())
        with open(f"tax_report_{WALLET[:8]}.txt", "w") as f:
            f.write(calc.generate_report())
        print(f"\n✅ Report saved")
    else:
        print("\n❌ No transactions found")