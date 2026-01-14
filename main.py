"""
Solana Memecoin Tax Calculator - WITH REGIONAL TAX SUPPORT
Supports tax calculations for different countries/regions with specific rules
"""
import requests
import time
import asyncio
import aiohttp
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
import json
import os
from enum import Enum

LAMPORTS_PER_SOL = 1_000_000_000
MAX_TRANSACTIONS = 10000
# Helius API rate limits:
# Free tier: 10 req/sec (0.1s delay)
# Paid tier: 50 req/sec (0.02s delay = 20ms)
# Using 0.02s for paid tier - adjust if you're on free tier
API_RATE_LIMIT_DELAY = 0.02  # 50 requests/second (paid tier)
# API_RATE_LIMIT_DELAY = 0.1  # 10 requests/second (free tier)
COINGECKO_DELAY = 0.02
DEXSCREENER_DELAY = 0.05
FLOAT_EPSILON = 0.0001
DEFAULT_SOL_PRICE_USD = 150.0
SOL_MINT_ADDRESS = 'So11111111111111111111111111111111111111112'
WSOL_MINT_ADDRESS = 'So11111111111111111111111111111111111111112'
USDC_MINT_ADDRESS = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'

class TaxRegion(Enum):
    """Supported tax regions with different rules"""
    US_FEDERAL = "us_federal"
    US_CALIFORNIA = "us_california"
    US_NEW_YORK = "us_new_york"
    US_TEXAS = "us_texas"
    US_FLORIDA = "us_florida"
    UK = "uk"
    INDIA = "india"
    GERMANY = "germany"
    AUSTRALIA = "australia"
    CANADA = "canada"

class TaxConfig:
    """Tax configuration for different regions"""
    
    CONFIGS = {
        TaxRegion.US_FEDERAL: {
            'name': 'United States (Federal)',
            'currency': 'USD',
            'short_term_threshold_days': 365,
            'short_term_rate': 0.37,  # Max federal rate
            'long_term_rate': 0.20,   # Max capital gains rate
            'has_state_tax': True,
            'wash_sale_applies': False,  # Crypto exempt from wash sale (for now)
            'description': 'Federal tax rates (highest bracket)',
        },
        TaxRegion.US_CALIFORNIA: {
            'name': 'California, USA',
            'currency': 'USD',
            'short_term_threshold_days': 365,
            'short_term_rate': 0.37 + 0.133,  # Federal + CA state (13.3%)
            'long_term_rate': 0.20 + 0.133,
            'has_state_tax': True,
            'wash_sale_applies': False,
            'description': 'Federal + California state tax (highest brackets)',
        },
        TaxRegion.US_NEW_YORK: {
            'name': 'New York, USA',
            'currency': 'USD',
            'short_term_threshold_days': 365,
            'short_term_rate': 0.37 + 0.109,  # Federal + NY state (10.9%)
            'long_term_rate': 0.20 + 0.109,
            'has_state_tax': True,
            'wash_sale_applies': False,
            'description': 'Federal + New York state tax (highest brackets)',
        },
        TaxRegion.US_TEXAS: {
            'name': 'Texas, USA',
            'currency': 'USD',
            'short_term_threshold_days': 365,
            'short_term_rate': 0.37,  # No state income tax
            'long_term_rate': 0.20,
            'has_state_tax': False,
            'wash_sale_applies': False,
            'description': 'Federal tax only (no state income tax)',
        },
        TaxRegion.US_FLORIDA: {
            'name': 'Florida, USA',
            'currency': 'USD',
            'short_term_threshold_days': 365,
            'short_term_rate': 0.37,  # No state income tax
            'long_term_rate': 0.20,
            'has_state_tax': False,
            'wash_sale_applies': False,
            'description': 'Federal tax only (no state income tax)',
        },
        TaxRegion.UK: {
            'name': 'United Kingdom',
            'currency': 'GBP',
            'short_term_threshold_days': 0,  # No distinction in UK
            'short_term_rate': 0.20,  # Capital Gains Tax rate
            'long_term_rate': 0.20,
            'annual_exemption': 6000,  # £6,000 tax-free allowance (2024)
            'has_state_tax': False,
            'wash_sale_applies': False,
            'description': '20% CGT on gains above £6,000 annual exemption',
        },
        TaxRegion.INDIA: {
            'name': 'India',
            'currency': 'INR',
            'short_term_threshold_days': 365,
            'short_term_rate': 0.30,  # 30% + cess
            'long_term_rate': 0.20,   # 20% with indexation
            'has_state_tax': False,
            'wash_sale_applies': False,
            'description': '30% on short-term, 20% on long-term gains',
        },
        TaxRegion.GERMANY: {
            'name': 'Germany',
            'currency': 'EUR',
            'short_term_threshold_days': 365,
            'short_term_rate': 0.45,  # Personal income tax (highest rate)
            'long_term_rate': 0.0,    # Tax-free if held >1 year!
            'has_state_tax': False,
            'wash_sale_applies': False,
            'description': 'Tax-free if held >1 year, otherwise up to 45%',
        },
        TaxRegion.AUSTRALIA: {
            'name': 'Australia',
            'currency': 'AUD',
            'short_term_threshold_days': 365,
            'short_term_rate': 0.45,  # Highest marginal rate
            'long_term_rate': 0.225,  # 50% CGT discount (45% * 0.5)
            'has_state_tax': False,
            'wash_sale_applies': False,
            'description': '50% discount on gains if held >1 year',
        },
        TaxRegion.CANADA: {
            'name': 'Canada',
            'currency': 'CAD',
            'short_term_threshold_days': 0,  # No distinction
            'short_term_rate': 0.535 * 0.5,  # 50% of gains taxable (highest rate)
            'long_term_rate': 0.535 * 0.5,
            'has_state_tax': True,  # Provincial taxes vary
            'wash_sale_applies': True,  # Superficial loss rules
            'description': '50% of gains included in income (highest bracket)',
        },
    }
    
    @classmethod
    def get_config(cls, region: TaxRegion) -> Dict:
        return cls.CONFIGS.get(region, cls.CONFIGS[TaxRegion.US_FEDERAL])

class SolanaMemecoinTaxCalculator:
    def __init__(self, wallet_address: str, helius_api_key: str, 
                 accounting_method: str = "FIFO", max_transactions: int = 1000,
                 tax_region: TaxRegion = TaxRegion.US_FEDERAL):
        self.wallet_address = wallet_address
        self.helius_api_key = helius_api_key
        self.accounting_method = accounting_method.upper()
        self.max_transactions = max_transactions
        self.tax_region = tax_region
        self.tax_config = TaxConfig.get_config(tax_region)
        
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
            'total_trades': 0,
            'short_term_gains': 0.0,
            'long_term_gains': 0.0,
        })
        self.sol_deposits = []
        self.sol_withdrawals = []
        self.sol_spent_trading = 0.0
        self.sol_received_trading = 0.0
        
        # Performance optimization: Pre-populate SOL metadata
        self.token_metadata[SOL_MINT_ADDRESS] = {
            'symbol': 'SOL',
            'name': 'Solana',
            'logoURI': 'https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/So11111111111111111111111111111111111111112/logo.png',
            'mint': SOL_MINT_ADDRESS
        }
    
    def _calculate_tax_liability(self, gain: float, holding_days: int) -> Tuple[float, str]:
        """Calculate tax liability based on holding period and region"""
        if gain <= 0:
            return 0.0, "N/A"
        
        threshold = self.tax_config['short_term_threshold_days']
        
        if holding_days >= threshold:
            rate = self.tax_config['long_term_rate']
            term_type = "Long-term"
        else:
            rate = self.tax_config['short_term_rate']
            term_type = "Short-term"
        
        tax = gain * rate
        return tax, term_type
    
    # [KEEP ALL THE EXISTING METHODS FROM main_optimized.py]
    # Including: fetch_wallet_transactions, _fetch_and_parse_async, etc.
    # I'll add them but condensed for brevity
    
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
        """
        Fetch transactions with optimized rate limiting for paid Helius tier (50 req/sec).
        Reduced delay from 0.3s to 0.02s to utilize full 50 req/sec capacity.
        """
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
                        
                        if total_fetched >= self.max_transactions:
                            print(f"Reached limit of {self.max_transactions} transactions")
                            break
                        
                        if len(data) < 100:
                            break
                            
                        before_signature = data[-1].get('signature')
                        # Reduced delay for paid tier (50 req/sec = 0.02s between requests)
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
                
                swaps = await asyncio.to_thread(self._parse_single_transaction, tx, PUMPFUN_PROGRAMS, None)
                
                if swaps:
                    parsed_swaps.extend(swaps)
                    processed_count += len(swaps)
                
            except Exception as e:
                print(f"Error processing transaction: {e}")
                continue
        
        pumpfun_count = sum(1 for s in parsed_swaps if s.get('is_pumpfun', False))
        print(f"Parsed {len(parsed_swaps)} swaps ({pumpfun_count} Pump.fun, {len(parsed_swaps) - pumpfun_count} other)")
        processing_complete.set()
    
    def _parse_single_transaction(self, tx: Dict, pumpfun_programs: List[str], cutoff_date: Optional[datetime]) -> List[Dict]:
        """Parse transaction - same as optimized version"""
        swaps = []
        
        try:
            timestamp = tx.get('timestamp')
            if not timestamp:
                return swaps
            
            date = datetime.fromtimestamp(timestamp)
            
            is_pumpfun = False
            source = tx.get('source', '')
            if source == 'PUMP_AMM' or 'PUMP' in source.upper():
                is_pumpfun = True
            
            wallet_lower = self.wallet_address.lower()
            
            net_sol_change = 0.0
            for account in tx.get('accountData', []):
                if account.get('account', '').lower() == wallet_lower:
                    net_sol_change = account.get('nativeBalanceChange', 0) / LAMPORTS_PER_SOL
                    break
            
            token_transfers = tx.get('tokenTransfers', [])
            if not token_transfers:
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
            
            tokens_in_dict = {}
            tokens_out_dict = {}
            
            for transfer in token_transfers:
                mint = transfer.get('mint', '')
                from_addr = transfer.get('fromUserAccount', '').lower()
                to_addr = transfer.get('toUserAccount', '').lower()
                amount = float(transfer.get('tokenAmount', 0))
                
                if mint == SOL_MINT_ADDRESS or mint == WSOL_MINT_ADDRESS or mint == USDC_MINT_ADDRESS:
                    continue
                
                if to_addr == wallet_lower:
                    tokens_in_dict[mint] = tokens_in_dict.get(mint, 0) + amount
                elif from_addr == wallet_lower:
                    tokens_out_dict[mint] = tokens_out_dict.get(mint, 0) + amount
            
            tokens_in = [{'mint': mint, 'amount': amt} for mint, amt in tokens_in_dict.items()]
            tokens_out = [{'mint': mint, 'amount': amt} for mint, amt in tokens_out_dict.items()]
            
            if net_sol_change < -FLOAT_EPSILON and tokens_in and not tokens_out:
                sol_spent = abs(net_sol_change)
                
                if len(tokens_in) == 1:
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
            
            elif net_sol_change > FLOAT_EPSILON and tokens_out and not tokens_in:
                sol_received = net_sol_change
                
                if len(tokens_out) == 1:
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
        
        except Exception as e:
            print(f"Error parsing transaction: {e}")
        
        return swaps
    
    async def _batch_fetch_metadata_async(self, mints: List[str]) -> Dict[str, Dict]:
        """Same as optimized version"""
        if not mints:
            return {}
        
        uncached_mints = [m for m in mints if m not in self.token_metadata and m != SOL_MINT_ADDRESS]
        
        if not uncached_mints:
            return {}
        
        print(f"Fetching metadata for {len(uncached_mints)} tokens in parallel...")
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for mint in uncached_mints:
                tasks.append(self._fetch_single_metadata_async(session, mint))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            metadata_dict = {}
            for mint, result in zip(uncached_mints, results):
                if isinstance(result, Exception):
                    continue
                if result:
                    self.token_metadata[mint] = result
                    metadata_dict[mint] = result
            
            return metadata_dict
    
    async def _fetch_single_metadata_async(self, session: aiohttp.ClientSession, mint: str) -> Optional[Dict]:
        """Fetch metadata and price data from DEX Screener"""
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()

                    if data.get('pairs') and len(data['pairs']) > 0:
                        pair = data['pairs'][0]
                        base_token = pair.get('baseToken', {})

                        symbol = base_token.get('symbol', '').strip()
                        name = base_token.get('name', '').strip()
                        logo = pair.get('info', {}).get('imageUrl', '')
                        price_usd = pair.get('priceUsd')

                        if symbol and name and symbol != 'N/A' and name != 'N/A':
                            await asyncio.sleep(DEXSCREENER_DELAY)
                            return {
                                'symbol': symbol,
                                'name': name,
                                'logoURI': logo,
                                'mint': mint,
                                'current_price_usd': float(price_usd) if price_usd else None
                            }
        except:
            pass

        return {
            'symbol': mint[:8],
            'name': f"Unknown ({mint[:8]}...)",
            'logoURI': '',
            'mint': mint,
            'current_price_usd': None
        }
    
    def _get_token_metadata(self, mint: str) -> Dict:
        if mint == SOL_MINT_ADDRESS or mint == 'SOL':
            return self.token_metadata[SOL_MINT_ADDRESS]
        
        if mint in self.token_metadata:
            return self.token_metadata[mint]
        
        fallback = {
            'symbol': mint[:8],
            'name': f"Unknown ({mint[:8]}...)",
            'logoURI': '',
            'mint': mint
        }
        self.token_metadata[mint] = fallback
        return fallback
    
    def _get_token_symbol(self, mint: str) -> str:
        return self._get_token_metadata(mint)['symbol']
    
    async def _batch_fetch_sol_prices_async(self, dates: List[datetime]) -> Dict[str, float]:
        """Same as optimized version"""
        unique_dates = list(set(date.strftime("%Y-%m-%d") for date in dates))
        uncached_dates = [d for d in unique_dates if d not in self.sol_price_cache]
        
        if not uncached_dates:
            return {}
        
        print(f"Fetching SOL prices for {len(uncached_dates)} unique dates in parallel...")
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for date_str in uncached_dates:
                tasks.append(self._fetch_single_sol_price_async(session, date_str))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for date_str, result in zip(uncached_dates, results):
                if isinstance(result, Exception):
                    self.sol_price_cache[date_str] = DEFAULT_SOL_PRICE_USD
                else:
                    self.sol_price_cache[date_str] = result
            
            return {}
    
    async def _fetch_single_sol_price_async(self, session: aiohttp.ClientSession, date_key: str) -> float:
        try:
            date_obj = datetime.strptime(date_key, "%Y-%m-%d")
            date_str = date_obj.strftime("%d-%m-%Y")
            url = f"https://api.coingecko.com/api/v3/coins/solana/history"
            
            async with session.get(
                url,
                params={'date': date_str, 'localization': 'false'},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'market_data' in data:
                        price = data['market_data']['current_price'].get('usd', DEFAULT_SOL_PRICE_USD)
                        await asyncio.sleep(COINGECKO_DELAY)
                        return price
        except:
            pass
        
        return DEFAULT_SOL_PRICE_USD
    
    def _get_sol_price_usd(self, date: datetime) -> float:
        date_key = date.strftime("%Y-%m-%d")
        return self.sol_price_cache.get(date_key, DEFAULT_SOL_PRICE_USD)
    
    def calculate_taxes_from_wallet(self, progress_callback=None):
        """Main calculation - same as optimized but with holding period tracking"""
        if progress_callback:
            progress_callback({'type': 'status', 'message': 'Fetching transactions...', 'data': {}})
        
        swaps = self.fetch_wallet_transactions(progress_callback)
        
        if not swaps:
            if progress_callback:
                progress_callback({'type': 'error', 'message': 'No swaps found', 'data': {}})
            return None
        
        swaps.sort(key=lambda x: x['date'])
        
        # Batch fetch metadata and prices
        all_mints = set()
        all_dates = []
        for swap in swaps:
            all_mints.add(swap['token_sold_mint'])
            all_mints.add(swap['token_bought_mint'])
            all_dates.append(swap['date'])
        
        all_mints.discard(SOL_MINT_ADDRESS)
        all_mints.discard(WSOL_MINT_ADDRESS)
        all_mints.discard(USDC_MINT_ADDRESS)
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(self._batch_fetch_metadata_async(list(all_mints)))
        loop.run_until_complete(self._batch_fetch_sol_prices_async(all_dates))
        
        # Process swaps
        for i, swap in enumerate(swaps):
            try:
                if (i + 1) % 50 == 0 and progress_callback:
                    progress_callback({
                        'type': 'progress',
                        'message': f"Processed {i + 1}/{len(swaps)}",
                        'data': {'processed': i + 1, 'total': len(swaps)}
                    })
                
                token_sold_mint = swap['token_sold_mint']
                token_bought_mint = swap['token_bought_mint']
                
                # Skip USDC transactions (treat like SOL deposits/withdrawals)
                if token_sold_mint == USDC_MINT_ADDRESS or token_bought_mint == USDC_MINT_ADDRESS:
                    continue
                
                token_sold_symbol = swap.get('token_sold_symbol') or self._get_token_symbol(token_sold_mint)
                token_bought_symbol = swap.get('token_bought_symbol') or self._get_token_symbol(token_bought_mint)
                
                amount_sold = swap['amount_sold']
                amount_bought = swap['amount_bought']
                
                sol_price = self._get_sol_price_usd(swap['date'])
                
                if token_sold_symbol == 'SOL':
                    usd_value = amount_sold * sol_price
                    usd_sold = usd_value
                    usd_bought = usd_value
                elif token_bought_symbol == 'SOL':
                    usd_value = amount_bought * sol_price
                    usd_sold = usd_value
                    usd_bought = usd_value
                else:
                    usd_sold = self._get_cost_basis_estimate(token_sold_symbol, amount_sold)
                    usd_bought = usd_sold
                
                # Process sale
                if token_sold_symbol != 'SOL':
                    self._process_sale(swap['date'], token_sold_symbol, token_sold_mint, amount_sold, usd_sold)
                
                # Process buy
                if token_bought_symbol != 'SOL':
                    self._process_buy(swap['date'], token_bought_symbol, amount_bought, usd_bought)
                
            except Exception as e:
                print(f"Error processing swap {i+1}: {e}")
        
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
    
    def _process_sale(self, sale_date: datetime, token: str, token_mint: str, amount: float, proceeds: float) -> float:
        """Process sale WITH holding period tracking"""
        if amount <= FLOAT_EPSILON:
            return 0
        
        stats = self.token_stats[token]
        stats['total_sold'] += amount
        stats['total_proceeds'] += proceeds
        stats['total_trades'] += 1
        if not stats['last_sale_date'] or sale_date > stats['last_sale_date']:
            stats['last_sale_date'] = sale_date
        
        if token not in self.holdings or not self.holdings[token]:
            gain = proceeds
            tax, term_type = self._calculate_tax_liability(gain, 0)
            
            token_meta = self._get_token_metadata(token_mint)
            
            self.taxable_events.append({
                'date': sale_date,
                'token': token_meta['symbol'],
                'token_name': token_meta['name'],
                'token_mint': token_mint,
                'amount': amount,
                'proceeds': proceeds,
                'cost_basis': 0,
                'capital_gain': gain,
                'holding_days': 0,
                'term_type': term_type,
                'tax_liability': tax
            })
            
            if term_type == "Short-term":
                stats['short_term_gains'] += gain
            else:
                stats['long_term_gains'] += gain
            
            return gain
        
        remaining = amount
        total_cost = 0.0
        weighted_holding_days = 0.0
        lots = self.holdings[token] if self.accounting_method == 'FIFO' else list(reversed(self.holdings[token]))
        
        while remaining > FLOAT_EPSILON and lots:
            lot = lots[0]
            from_lot = min(remaining, lot['amount'])
            
            # Calculate holding period for this lot
            holding_days = (sale_date - lot['date']).days
            weighted_holding_days += holding_days * (from_lot / amount)
            
            total_cost += from_lot * lot['cost_basis_per_unit']
            lot['amount'] -= from_lot
            remaining -= from_lot
            
            if lot['amount'] < FLOAT_EPSILON:
                lots.pop(0)
                if self.accounting_method == 'LIFO':
                    self.holdings[token].pop()
        
        gain = proceeds - total_cost
        avg_holding_days = int(weighted_holding_days)
        tax, term_type = self._calculate_tax_liability(gain, avg_holding_days)
        
        token_meta = self._get_token_metadata(token_mint)
        
        self.taxable_events.append({
            'date': sale_date,
            'token': token_meta['symbol'],
            'token_name': token_meta['name'],
            'token_mint': token_mint,
            'amount': amount,
            'proceeds': proceeds,
            'cost_basis': total_cost,
            'capital_gain': gain,
            'holding_days': avg_holding_days,
            'term_type': term_type,
            'tax_liability': tax
        })
        
        if term_type == "Short-term":
            stats['short_term_gains'] += gain
        else:
            stats['long_term_gains'] += gain
        
        return gain
    
    def generate_report(self) -> str:
        """Enhanced report with regional tax information"""
        total_gains = sum(e['capital_gain'] for e in self.taxable_events)
        total_proceeds = sum(e['proceeds'] for e in self.taxable_events)
        total_cost = sum(e['cost_basis'] for e in self.taxable_events)
        
        short_term_gains = sum(e['capital_gain'] for e in self.taxable_events if e.get('term_type') == 'Short-term')
        long_term_gains = sum(e['capital_gain'] for e in self.taxable_events if e.get('term_type') == 'Long-term')
        
        gains_by_token = defaultdict(float)
        for e in self.taxable_events:
            gains_by_token[e['token']] += e['capital_gain']
        
        report = []
        report.append("=" * 90)
        report.append("SOLANA MEMECOIN TAX REPORT")
        report.append(f"Region: {self.tax_config['name']}")
        report.append(f"Wallet: {self.wallet_address}")
        report.append(f"Accounting Method: {self.accounting_method}")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 90)
        report.append("")
        
        report.append("TAX CONFIGURATION")
        report.append("-" * 90)
        report.append(f"Description: {self.tax_config['description']}")
        report.append(f"Short-term rate: {self.tax_config['short_term_rate']*100:.1f}%")
        report.append(f"Long-term rate: {self.tax_config['long_term_rate']*100:.1f}%")
        if 'annual_exemption' in self.tax_config:
            report.append(f"Annual exemption: {self.tax_config['currency']} {self.tax_config['annual_exemption']:,.0f}")
        report.append("")
        
        report.append("TAX SUMMARY")
        report.append("-" * 90)
        report.append(f"Total Taxable Sales: {len(self.taxable_events)}")
        report.append(f"Total Proceeds: ${total_proceeds:,.2f}")
        report.append(f"Total Cost Basis: ${total_cost:,.2f}")
        report.append(f"NET CAPITAL GAIN/LOSS: ${total_gains:,.2f}")
        report.append("")
        report.append(f"Short-term gains (≤1 year): ${short_term_gains:,.2f}")
        report.append(f"Long-term gains (>1 year): ${long_term_gains:,.2f}")
        report.append("")
        
        report.append("TOKEN PERFORMANCE (Top 20 by absolute gain/loss)")
        report.append("-" * 90)
        report.append(f"{'Token':<15} {'Invested':<12} {'Proceeds':<12} {'Gain/Loss':<12} {'ROI':<10} {'Trades':<8}")
        report.append("-" * 90)
        
        filtered = [(t, g) for t, g in gains_by_token.items() if t != 'SOL']
        sorted_tokens = sorted(filtered, key=lambda x: abs(x[1]), reverse=True)[:20]
        
        for token, gain in sorted_tokens:
            stats = self.token_stats[token]
            invested = stats['total_cost']
            proceeds = stats['total_proceeds']
            roi = (gain / invested * 100) if invested > 0 else 0
            trades = stats['total_trades']
            
            report.append(f"{token:<15} ${invested:<11,.2f} ${proceeds:<11,.2f} ${gain:<11,.2f} {roi:>8.1f}% {trades:<8}")
        
        report.append("")
        report.append("=" * 90)
        report.append("IMPORTANT DISCLAIMER")
        report.append("=" * 90)
        report.append("This report is for informational purposes only and should NOT be considered")
        report.append("professional tax advice. Tax laws vary by jurisdiction and change frequently.")
        report.append("Please consult with a qualified tax professional or accountant in your region")
        report.append("before filing any tax returns or making tax-related decisions.")
        report.append("")
        report.append("The short-term and long-term gains are provided to help you understand your")
        report.append("tax position. You should calculate your actual tax liability based on your")
        report.append("specific tax bracket, deductions, and other factors with a tax professional.")
        report.append("=" * 90)
        
        return "\n".join(report)
    
    def generate_json_report(self) -> Dict:
        """Enhanced JSON report with tax details"""
        total_gains = sum(e['capital_gain'] for e in self.taxable_events)
        total_proceeds = sum(e['proceeds'] for e in self.taxable_events)
        total_cost = sum(e['cost_basis'] for e in self.taxable_events)
        total_tax = sum(e.get('tax_liability', 0) for e in self.taxable_events)
        
        short_term_gains = sum(e['capital_gain'] for e in self.taxable_events if e.get('term_type') == 'Short-term')
        long_term_gains = sum(e['capital_gain'] for e in self.taxable_events if e.get('term_type') == 'Long-term')
        
        gains_by_mint = defaultdict(float)
        for e in self.taxable_events:
            mint = e.get('token_mint', '')
            if mint and mint != SOL_MINT_ADDRESS:
                gains_by_mint[mint] += e['capital_gain']
        
        tokens_list = []
        for mint, gain in sorted(gains_by_mint.items(), key=lambda x: abs(x[1]), reverse=True)[:50]:
            meta = self._get_token_metadata(mint)
            symbol = meta['symbol']
            stats = self.token_stats[symbol]
            
            roi = (gain / stats['total_cost'] * 100) if stats['total_cost'] > 0 else 0
            
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
                'short_term_gains': round(stats['short_term_gains'], 2),
                'long_term_gains': round(stats['long_term_gains'], 2),
            })
        
        events_list = []
        for e in sorted(self.taxable_events, key=lambda x: x['date'], reverse=True)[:100]:
            events_list.append({
                'date': e['date'].strftime('%Y-%m-%d %H:%M'),
                'token': e['token'],
                'token_name': e.get('token_name', e['token']),
                'amount': round(e['amount'], 6),
                'proceeds': round(e['proceeds'], 2),
                'cost': round(e['cost_basis'], 2),
                'gain': round(e['capital_gain'], 2),
                'holding_days': e.get('holding_days', 0),
                'term_type': e.get('term_type', 'N/A')
            })
        
        return {
            'wallet': self.wallet_address,
            'accounting_method': self.accounting_method,
            'tax_region': self.tax_region.value,
            'tax_config': self.tax_config,
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_proceeds': round(total_proceeds, 2),
                'total_cost': round(total_cost, 2),
                'net_gain': round(total_gains, 2),
                'short_term_gains': round(short_term_gains, 2),
                'long_term_gains': round(long_term_gains, 2),
                'taxable_sales': len(self.taxable_events),
            },
            'tokens': tokens_list,
            'events': events_list,
            'full_report_text': self.generate_report()
        }


if __name__ == "__main__":
    print("Solana Memecoin Tax Calculator - REGIONAL SUPPORT")
    print("=" * 80)
    
    # Example: Calculate for different regions
    API_KEY = os.environ.get('HELIUS_API_KEY', '32c0f32e-9d6c-4658-9982-f0b2f0342b23')
    WALLET = os.environ.get('WALLET_ADDRESS', '4yKnfzcf98jm5z3uHvBXjLa9vFB713jWfnWDcpWZCqpH')
    
    # Choose your region here
    REGION = TaxRegion.US_CALIFORNIA  # Change this!
    
    print(f"Calculating taxes for region: {TaxConfig.get_config(REGION)['name']}")
    print("")
    
    calc = SolanaMemecoinTaxCalculator(WALLET, API_KEY, "FIFO", tax_region=REGION)
    result = calc.calculate_taxes_from_wallet()
    
    if result:
        print("\n" + calc.generate_report())
        
        region_name = REGION.value
        with open(f"tax_report_{WALLET[:8]}_{region_name}.txt", "w") as f:
            f.write(calc.generate_report())
        
        with open(f"tax_report_{WALLET[:8]}_{region_name}.json", "w") as f:
            json.dump(calc.generate_json_report(), f, indent=2)
        
        print(f"\n✅ Reports saved for {region_name}")
    else:
        print("\n❌ No transactions found")