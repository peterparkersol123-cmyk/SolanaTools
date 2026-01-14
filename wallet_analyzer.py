"""
Wallet Analyzer Module - FIXED with time period filtering
Analyzes Solana wallet trading patterns and performance
"""
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Optional
import statistics
import logging

logger = logging.getLogger(__name__)

class WalletAnalyzer:
    def __init__(self, wallet_address: str, calculator, time_period_hours: Optional[int] = None):
        """
        Initialize with wallet address and SolanaMemecoinTaxCalculator instance
        
        Args:
            time_period_hours: Filter to last N hours (None = all time)
                - 24 = last 24 hours (rolling window)
                - 168 = last 7 days
                - None = all time
        """
        self.wallet_address = wallet_address
        self.calculator = calculator
        self.time_period_hours = time_period_hours
        self.trades = []
        self.tokens_traded = set()
        
        # Calculate cutoff time if period specified (ROLLING WINDOW)
        self.cutoff_time = None
        if time_period_hours is not None:
            self.cutoff_time = datetime.now() - timedelta(hours=time_period_hours)
            logger.info(f"Filtering trades after: {self.cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
    def analyze(self) -> Dict:
        """Main analysis function"""
        # Process taxable events into trades (with time filtering)
        self._process_taxable_events()
        
        # Calculate statistics
        stats = self._calculate_stats()
        activity_timeline = self._get_activity_timeline()
        pnl_distribution = self._get_pnl_distribution()
        top_performers, worst_performers = self._get_top_performers()
        current_holdings = self._get_current_holdings()
        hold_time_analysis = self._get_hold_time_analysis()
        
        return {
            'wallet': self.wallet_address,
            'time_period': f"{self.time_period_hours}h" if self.time_period_hours else "all_time",
            'cutoff_time': self.cutoff_time.isoformat() if self.cutoff_time else None,
            'stats': stats,
            'activity_timeline': activity_timeline,
            'pnl_distribution': pnl_distribution,
            'top_performers': top_performers,
            'worst_performers': worst_performers,
            'current_holdings': current_holdings,
            'hold_time_analysis': hold_time_analysis,
            'analyzed_at': datetime.now().isoformat()
        }
    
    def _process_taxable_events(self):
        """Process taxable events from calculator with time filtering"""
        # Tokens to exclude (stablecoins and deposits)
        EXCLUDED_TOKENS = {'USDC', 'USDT', 'DAI', 'BUSD', 'UST', 'FRAX', 'SOL'}
        
        filtered_count = 0
        total_count = 0
        
        for event in self.calculator.taxable_events:
            total_count += 1
            event_date = event.get('date')
            token = event.get('token', 'Unknown')
            
            # Skip excluded tokens (stablecoins)
            if token in EXCLUDED_TOKENS:
                filtered_count += 1
                continue
            
            # Apply time filter if set
            if self.cutoff_time and event_date < self.cutoff_time:
                filtered_count += 1
                continue  # Skip events before cutoff
            
            self.tokens_traded.add(token)
            
            self.trades.append({
                'type': 'SELL',
                'date': event_date,
                'token': token,
                'token_mint': event.get('token_mint', ''),
                'amount': event.get('amount', 0),
                'proceeds': event.get('proceeds', 0),
                'cost': event.get('cost_basis', 0),
                'pnl': event.get('capital_gain', 0),
                'hold_days': event.get('holding_days', 0)
            })
        
        if self.cutoff_time:
            logger.info(f"Filtered {filtered_count} events (stablecoins + time filter), kept {len(self.trades)} events")
        else:
            logger.info(f"Filtered {filtered_count} stablecoin events, kept {len(self.trades)} events")
    
    def _calculate_stats(self) -> Dict:
        """Calculate trading statistics"""
        sells = [t for t in self.trades if t['type'] == 'SELL']

        if not sells:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_gain': 0,
                'avg_loss': 0,
                'largest_win': 0,
                'largest_loss': 0,
                'avg_hold_time': 0,
                'tokens_traded': 0
            }

        # Calculate P/L per token (aggregate all transactions for each token)
        token_pnl = defaultdict(float)
        for trade in sells:
            token_pnl[trade['token']] += trade['pnl']

        # Debug output
        logger.debug(f"\n=== TOKEN P&L BREAKDOWN ===")
        for token, pnl in sorted(token_pnl.items(), key=lambda x: x[1], reverse=True):
            logger.debug(f"{token}: ${pnl:.2f}")

        # Count wins/losses based on total P/L per token
        # Winners: any P&L > $0.01 (excludes tiny rounding errors)
        # Losers: any P&L < -$0.01 (excludes tiny rounding errors)
        # Near-zero trades (-$0.01 to $0.01) are excluded from win rate calculation
        THRESHOLD = 0.01
        winning_tokens = [pnl for pnl in token_pnl.values() if pnl > THRESHOLD]
        losing_tokens = [pnl for pnl in token_pnl.values() if pnl < -THRESHOLD]
        breakeven_tokens = [pnl for pnl in token_pnl.values() if -THRESHOLD <= pnl <= THRESHOLD]

        # Calculate counts
        num_winners = len(winning_tokens)
        num_losers = len(losing_tokens)
        num_breakeven = len(breakeven_tokens)

        logger.debug(f"Winners: {num_winners}, Losers: {num_losers}, Breakeven: {num_breakeven}")

        # Overall stats
        total_pnl = sum(token_pnl.values())
        avg_gain = sum(winning_tokens) / num_winners if num_winners else 0
        avg_loss = sum(losing_tokens) / num_losers if num_losers else 0

        largest_win = max(winning_tokens, default=0)
        largest_loss = min(losing_tokens, default=0)

        hold_times = [t.get('hold_days', 0) for t in sells if 'hold_days' in t]
        avg_hold_days = statistics.mean(hold_times) if hold_times else 0

        # WIN RATE: winners / (winners + losers) * 100
        # Breakeven trades (within ±$0.01) are excluded from win rate
        total_decided = num_winners + num_losers
        win_rate = (num_winners / total_decided * 100) if total_decided > 0 else 0

        logger.debug(f"Win Rate Calculation: {num_winners} / {total_decided} = {win_rate:.1f}% ({num_breakeven} breakeven excluded)")

        # Format hold time intelligently
        if avg_hold_days >= 1:
            # 1+ days: show as days
            hold_time_value = round(avg_hold_days, 1)
            hold_time_unit = 'days'
        elif avg_hold_days >= 1/24:  # >= 1 hour
            # Show as hours
            hold_time_value = round(avg_hold_days * 24, 1)
            hold_time_unit = 'hours'
        elif avg_hold_days >= 1/1440:  # >= 1 minute
            # Show as minutes
            hold_time_value = round(avg_hold_days * 1440, 1)
            hold_time_unit = 'mins'
        else:
            # Show as seconds
            hold_time_value = round(avg_hold_days * 86400, 1)
            hold_time_unit = 'secs'

        return {
            'total_trades': len(sells),
            'winning_trades': num_winners,
            'losing_trades': num_losers,
            'win_rate': round(win_rate, 1),
            'total_pnl': round(total_pnl, 2),
            'avg_gain': round(avg_gain, 2),
            'avg_loss': round(avg_loss, 2),
            'largest_win': round(largest_win, 2),
            'largest_loss': round(largest_loss, 2),
            'avg_hold_time': hold_time_value,
            'avg_hold_time_unit': hold_time_unit,
            'tokens_traded': len(self.tokens_traded)
        }
    
    def _get_activity_timeline(self) -> List[Dict]:
        """Get trading activity over time (daily)"""
        if not self.trades:
            return []
        
        # Group by date
        activity_by_date = defaultdict(lambda: {'count': 0, 'pnl': 0})
        for trade in self.trades:
            date_key = trade['date'].strftime('%Y-%m-%d')
            activity_by_date[date_key]['count'] += 1
            activity_by_date[date_key]['pnl'] += trade.get('pnl', 0)
        
        # Sort by date and return last 30 days
        sorted_dates = sorted(activity_by_date.items())[-30:]
        
        return [
            {
                'date': date,
                'count': data['count'],
                'pnl': round(data['pnl'], 2)
            }
            for date, data in sorted_dates
        ]
    
    def _get_pnl_distribution(self) -> List[Dict]:
        """Get P/L distribution buckets"""
        sells = [t for t in self.trades if t['type'] == 'SELL']
        
        if not sells:
            return []
        
        # Define buckets
        buckets = [
            ('<-$100', lambda x: x < -100),
            ('-$100 to -$50', lambda x: -100 <= x < -50),
            ('-$50 to -$10', lambda x: -50 <= x < -10),
            ('-$10 to $0', lambda x: -10 <= x < 0),
            ('$0 to $10', lambda x: 0 <= x < 10),
            ('$10 to $50', lambda x: 10 <= x < 50),
            ('$50 to $100', lambda x: 50 <= x < 100),
            ('>$100', lambda x: x >= 100)
        ]
        
        distribution = []
        for label, condition in buckets:
            count = sum(1 for t in sells if condition(t['pnl']))
            if count > 0:
                distribution.append({'range': label, 'count': count})
        
        return distribution
    
    def _get_top_performers(self) -> tuple:
        """Get top and worst performing tokens"""
        # Tokens to exclude (stablecoins and deposits)
        EXCLUDED_TOKENS = {'USDC', 'USDT', 'DAI', 'BUSD', 'UST', 'FRAX', 'SOL'}
        
        # Aggregate P/L by token
        token_performance = defaultdict(lambda: {'pnl': 0, 'trades': 0, 'symbol': '', 'cost': 0})
        
        for trade in self.trades:
            if trade['type'] == 'SELL':
                token = trade['token']
                
                # Skip excluded tokens
                if token in EXCLUDED_TOKENS:
                    continue
                    
                token_performance[token]['pnl'] += trade['pnl']
                token_performance[token]['trades'] += 1
                token_performance[token]['symbol'] = trade['token']
                token_performance[token]['cost'] += trade['cost']
        
        # Sort by P/L
        sorted_tokens = sorted(
            [
                {
                    'symbol': data['symbol'],
                    'pnl': round(data['pnl'], 2),
                    'trades': data['trades'],
                    'roi': round((data['pnl'] / data['cost'] * 100), 1) if data['cost'] > 0 else 0
                }
                for token, data in token_performance.items()
            ],
            key=lambda x: x['pnl'],
            reverse=True
        )
        
        top_5 = sorted_tokens[:5]
        worst_5 = sorted_tokens[-5:][::-1]
        
        return top_5, worst_5
    
    def _get_current_holdings(self) -> List[Dict]:
        """Get current token holdings from calculator"""
        # Tokens to exclude (stablecoins and deposits)
        EXCLUDED_TOKENS = {'USDC', 'USDT', 'DAI', 'BUSD', 'UST', 'FRAX', 'SOL'}

        holdings = []

        # The calculator.holdings is a defaultdict(list) of token lots
        for token, lots in self.calculator.holdings.items():
            if not lots:
                continue

            # Skip excluded tokens
            if token in EXCLUDED_TOKENS:
                continue

            # Only sum lots that still have remaining amount (not fully sold)
            total_amount = sum(lot['amount'] for lot in lots if lot['amount'] > 0)
            total_cost = sum(lot['total_cost_basis'] for lot in lots if lot['amount'] > 0)

            if total_amount > 0.001:  # Only show non-zero holdings
                holdings.append({
                    'symbol': token,
                    'name': token,  # Could enhance with metadata lookup
                    'amount': round(total_amount, 2),
                    'cost_basis': round(total_cost, 2),
                    'value': round(total_cost, 2)  # Would need current price for real value
                })

        return sorted(holdings, key=lambda x: x['value'], reverse=True)
    
    def _get_hold_time_analysis(self) -> Dict:
        """Analyze holding periods"""
        sells = [t for t in self.trades if t['type'] == 'SELL' and 'hold_days' in t]
        
        if not sells:
            return {
                'avg_hold_days': 0,
                'median_hold_days': 0,
                'quick_trades': 0,  # < 1 day
                'swing_trades': 0,  # 1-7 days
                'position_trades': 0,  # 7-30 days
                'long_holds': 0  # > 30 days
            }
        
        hold_days = [t['hold_days'] for t in sells]
        
        return {
            'avg_hold_days': round(statistics.mean(hold_days), 1),
            'median_hold_days': round(statistics.median(hold_days), 1),
            'quick_trades': sum(1 for d in hold_days if d < 1),
            'swing_trades': sum(1 for d in hold_days if 1 <= d < 7),
            'position_trades': sum(1 for d in hold_days if 7 <= d < 30),
            'long_holds': sum(1 for d in hold_days if d >= 30)
        }