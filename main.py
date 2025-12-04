"""Index Fund Replication Calculator.

This module calculates the number of shares to buy for each equity in an index fund
based on market cap weighting with a 15% cap per equity.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def load_fund_data(file_path: str) -> List[Dict]:
    """Load index fund data from JSON file.
    
    Args:
        file_path: Path to the JSON file containing fund data.
        
    Returns:
        List of dictionaries containing equity information.
        
    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    fund_path = Path(file_path)
    if not fund_path.exists():
        raise FileNotFoundError(f"Fund data file not found: {file_path}")
    
    with open(fund_path, "r", encoding="utf-8") as funds:
        data = json.load(funds)
    return data


def calculate_weights_with_cap(
    equities: List[Dict], cap_percentage: float = 0.15
) -> Dict[str, float]:
    """Calculate weights for each equity based on market cap with a cap.
    
    Args:
        equities: List of equity dictionaries with 'ticker' and 'market_cap' keys.
        cap_percentage: Maximum weight allowed for any single equity (default: 0.15).
        
    Returns:
        Dictionary mapping ticker to weight (0.0 to 1.0).
    """
    # Calculate total market cap
    total_market_cap = sum(equity["market_cap"] for equity in equities)
    
    if total_market_cap == 0:
        raise ValueError("Total market cap is zero")
    
    # Calculate initial weights based on market cap
    initial_weights = {
        equity["ticker"]: equity["market_cap"] / total_market_cap
        for equity in equities
    }
    
    # Apply cap and redistribute excess weight
    capped_weights = {}
    excess_weight = 0.0
    
    for ticker, weight in initial_weights.items():
        if weight > cap_percentage:
            capped_weights[ticker] = cap_percentage
            excess_weight += weight - cap_percentage
        else:
            capped_weights[ticker] = weight
    
    # Redistribute excess weight proportionally to non-capped equities
    if excess_weight > 0:
        # Get equities that are not capped
        non_capped_equities = [
            ticker for ticker, weight in initial_weights.items()
            if initial_weights[ticker] <= cap_percentage
        ]
        
        if non_capped_equities:
            # Calculate total weight of non-capped equities
            non_capped_total = sum(
                initial_weights[ticker] for ticker in non_capped_equities
            )
            
            if non_capped_total > 0:
                # Redistribute excess proportionally
                for ticker in non_capped_equities:
                    redistribution_factor = initial_weights[ticker] / non_capped_total
                    capped_weights[ticker] += excess_weight * redistribution_factor
                    # Ensure we don't exceed cap after redistribution
                    capped_weights[ticker] = min(
                        capped_weights[ticker], cap_percentage
                    )
    
    return capped_weights


def calculate_shares(
    equities: List[Dict],
    investment_amount: float,
    transaction_cost_rate: float = 0.03,
    cap_percentage: float = 0.15,
) -> Tuple[Dict[str, int], float, float]:
    """Calculate number of shares to buy for each equity in the fund.
    
    Args:
        equities: List of equity dictionaries with 'ticker', 'price', and 'market_cap'.
        investment_amount: Total amount to invest.
        transaction_cost_rate: Transaction cost as a percentage (default: 0.03 for 3%).
        cap_percentage: Maximum weight allowed for any single equity (default: 0.15).
        
    Returns:
        Tuple containing:
            - Dictionary mapping ticker to number of shares to buy
            - Total cost including transaction fees
            - Total cost excluding transaction fees
    """
    if investment_amount <= 0:
        raise ValueError("Investment amount must be positive")
    
    # Create a dictionary for easy lookup
    equity_dict = {equity["ticker"]: equity for equity in equities}
    
    # Calculate weights with cap
    weights = calculate_weights_with_cap(equities, cap_percentage)
    
    # Calculate shares and costs
    shares_per_ticker = {}
    total_cost_excl_fees = 0.0
    
    for ticker, weight in weights.items():
        equity = equity_dict[ticker]
        price = equity["price"]
        
        if price <= 0:
            raise ValueError(f"Invalid price for {ticker}: {price}")
        
        # Amount to invest in this equity
        allocation = investment_amount * weight
        
        # Calculate number of shares (before transaction cost)
        # We need to account for transaction cost when calculating shares
        # If we invest X, and transaction cost is 3%, then:
        # X = shares * price * (1 + transaction_cost_rate)
        # So: shares = X / (price * (1 + transaction_cost_rate))
        shares = int(allocation / (price * (1 + transaction_cost_rate)))
        shares_per_ticker[ticker] = shares
        
        # Cost for this equity (shares * price)
        cost_excl_fees = shares * price
        total_cost_excl_fees += cost_excl_fees
    
    # Calculate total transaction fees
    total_transaction_fees = total_cost_excl_fees * transaction_cost_rate
    total_cost_incl_fees = total_cost_excl_fees + total_transaction_fees
    
    return shares_per_ticker, total_cost_incl_fees, total_cost_excl_fees


def replicate_index_fund(
    fund_file: str,
    investment_amount: float,
    transaction_cost_rate: float = 0.03,
    cap_percentage: float = 0.15,
) -> Tuple[Dict[str, int], float, float]:
    """Replicate an index fund by determining shares to buy for each equity.
    
    Args:
        fund_file: Path to JSON file containing fund data.
        investment_amount: Total amount to invest.
        transaction_cost_rate: Transaction cost as a percentage (default: 0.03).
        cap_percentage: Maximum weight allowed for any single equity (default: 0.15).
        
    Returns:
        Tuple containing:
            - Dictionary mapping ticker to number of shares to buy
            - Total cost including transaction fees
            - Total cost excluding transaction fees
    """
    # Load fund data
    equities = load_fund_data(fund_file)
    
    if not equities:
        raise ValueError("Fund data is empty")
    
    # Calculate shares
    shares, total_cost_incl, total_cost_excl = calculate_shares(
        equities, investment_amount, transaction_cost_rate, cap_percentage
    )
    
    return shares, total_cost_incl, total_cost_excl


def main():
    """Main function to run the index fund replication calculator."""
    parser = argparse.ArgumentParser(
        description="Calculate shares to buy for index fund replication"
    )
    parser.add_argument(
        "--investment",
        type=float,
        default=50000.0,
        help="Investment amount (default: 50000)",
    )
    parser.add_argument(
        "--fund-file",
        type=str,
        default="index_funds/afribank.json",
        help="Path to fund data JSON file (default: index_funds/afribank.json)",
    )
    parser.add_argument(
        "--transaction-cost",
        type=float,
        default=0.03,
        help="Transaction cost rate as decimal (default: 0.03 for 3%%)",
    )
    parser.add_argument(
        "--cap",
        type=float,
        default=0.2,
        help="Maximum weight per equity as decimal (default: 0.15 for 15%%)",
    )
    
    args = parser.parse_args()
    
    try:
        # Calculate shares
        shares, total_cost_incl, total_cost_excl = replicate_index_fund(
            args.fund_file,
            args.investment,
            args.transaction_cost,
            args.cap,
        )
        
        # Display results
        print(f"\nInvestment Amount: N{args.investment:,.2f}")
        print(f"Transaction Cost Rate: {args.transaction_cost * 100:.1f}%")
        print(f"Maximum Weight Per Equity: {args.cap * 100:.1f}%")
        print("\n" + "=" * 80)
        print("SHARES TO BUY PER TICKER:")
        print("=" * 80)
        
        for ticker, num_shares in sorted(shares.items()):
            if num_shares > 0:
                print(f"{ticker:15s}: {num_shares:6d} shares")
        
        print("=" * 80)
        print(f"\nTotal Cost (excluding fees): N{total_cost_excl:,.2f}")
        print(f"Total Transaction Fees: N{(total_cost_incl - total_cost_excl):,.2f}")
        print(f"Total Cost (including fees): N{total_cost_incl:,.2f}")
        print(f"\nRemaining Cash: N{(args.investment - total_cost_incl):,.2f}")
        
        return shares, total_cost_incl, total_cost_excl
        
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
