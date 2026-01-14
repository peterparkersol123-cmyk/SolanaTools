"""
AI Tax Optimization Assistant
Provides intelligent tax advice and optimization suggestions using Claude
"""
import os
import json
from typing import Dict, List, Optional
from datetime import datetime
from anthropic import Anthropic

class TaxAssistant:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the tax assistant with Anthropic API key"""
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter.")

        self.client = Anthropic(api_key=self.api_key)
        self.conversation_history = []

    def get_system_prompt(self, tax_data: Dict) -> str:
        """Generate system prompt with user's tax context"""
        return f"""You are an expert tax optimization assistant specializing in cryptocurrency trading taxes.
You have access to the user's complete tax data and trading history.

IMPORTANT CONTEXT:
- Tax Region: {tax_data.get('tax_region', 'Unknown')}
- Accounting Method: {tax_data.get('accounting_method', 'FIFO')}
- Total P&L: ${tax_data.get('total_pnl', 0):,.2f}
- Total Tax Liability: ${tax_data.get('total_tax_liability', 0):,.2f}
- Total Trades: {tax_data.get('total_trades', 0)}
- Winning Trades: {tax_data.get('winning_trades', 0)}
- Losing Trades: {tax_data.get('losing_trades', 0)}
- Current Holdings Value: ${tax_data.get('holdings_value', 0):,.2f}

TAX RATES:
- Short-term (<365 days): {tax_data.get('short_term_rate', 0)*100}%
- Long-term (≥365 days): {tax_data.get('long_term_rate', 0)*100}%

AVAILABLE DATA:
{json.dumps(tax_data, indent=2, default=str)}

YOUR ROLE:
1. Provide accurate, actionable tax optimization advice
2. Explain complex tax concepts in simple terms
3. Suggest specific strategies like tax-loss harvesting, timing of sales, FIFO vs LIFO optimization
4. Answer "what-if" scenarios about potential trades
5. Identify opportunities to reduce tax burden legally
6. Warn about risks like wash sale rules (if applicable in their region)

GUIDELINES:
- Always cite specific numbers from their data
- Be conversational and helpful, not overly formal
- Include disclaimers when appropriate (e.g., "This is educational information, consult a tax professional")
- Focus on practical, implementable advice
- If you don't have enough data to answer, ask clarifying questions

LIMITATIONS:
- You cannot provide personalized tax advice (not a licensed CPA)
- Always recommend consulting a tax professional for major decisions
- Crypto tax law varies by jurisdiction and changes frequently
"""

    def chat(self, user_message: str, tax_data: Dict) -> str:
        """
        Send a message to the AI assistant and get a response

        Args:
            user_message: The user's question or request
            tax_data: Complete tax calculation data and holdings

        Returns:
            AI assistant's response
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Generate system prompt with current tax data
        system_prompt = self.get_system_prompt(tax_data)

        # Call Claude API
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                system=system_prompt,
                messages=self.conversation_history
            )

            # Extract assistant's response
            assistant_message = response.content[0].text

            # Add to conversation history
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })

            return assistant_message

        except Exception as e:
            return f"Sorry, I encountered an error: {str(e)}. Please try again."

    def reset_conversation(self):
        """Clear conversation history"""
        self.conversation_history = []

    def get_suggestions(self, tax_data: Dict) -> List[str]:
        """
        Generate proactive tax optimization suggestions based on the data

        Returns:
            List of actionable suggestions
        """
        suggestions = []

        # Tax loss harvesting opportunity
        unrealized_losses = tax_data.get('unrealized_losses', 0)
        if unrealized_losses < -100:
            tax_rate = tax_data.get('short_term_rate', 0.37)
            potential_savings = abs(unrealized_losses) * tax_rate
            suggestions.append({
                'title': 'Tax-Loss Harvesting Opportunity',
                'description': f'You have ${abs(unrealized_losses):,.2f} in unrealized losses. Harvesting these could save you approximately ${potential_savings:,.2f} in taxes.',
                'priority': 'high',
                'action': 'Consider selling losing positions to offset gains'
            })

        # Long-term vs short-term optimization
        short_term_gains = tax_data.get('short_term_gains', 0)
        long_term_gains = tax_data.get('long_term_gains', 0)

        if short_term_gains > long_term_gains * 2:
            short_rate = tax_data.get('short_term_rate', 0.37)
            long_rate = tax_data.get('long_term_rate', 0.20)
            potential_savings = short_term_gains * (short_rate - long_rate)

            suggestions.append({
                'title': 'Consider Holding Longer',
                'description': f'Most of your gains are short-term (taxed at {short_rate*100}%). If you held positions for >365 days, you could save {(short_rate-long_rate)*100}% in taxes.',
                'priority': 'medium',
                'action': f'Potential annual savings: ${potential_savings:,.2f} by holding winners longer'
            })

        # FIFO vs LIFO optimization
        accounting_method = tax_data.get('accounting_method', 'FIFO')
        if accounting_method == 'FIFO':
            suggestions.append({
                'title': 'Consider LIFO for Recent Buys',
                'description': 'FIFO sells your oldest positions first. If you recently bought at higher prices, LIFO might reduce your gains.',
                'priority': 'low',
                'action': 'Run a comparison between FIFO and LIFO methods'
            })

        # High-frequency trading warning
        total_trades = tax_data.get('total_trades', 0)
        if total_trades > 500:
            suggestions.append({
                'title': 'High Trading Frequency Detected',
                'description': f'You made {total_trades} trades. High-frequency trading usually results in more short-term gains (higher taxes) and potential pattern day trader classification.',
                'priority': 'medium',
                'action': 'Consider a more patient buy-and-hold strategy for tax efficiency'
            })

        return suggestions
