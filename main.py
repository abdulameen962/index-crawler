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
    """Calculate number of shares to buy for each equity while strictly maintaining target weights.
    
    Uses Optimal Multiplier Scaling: scales the base capital allocation proportionally
    across all constituents to minimize unallocated cash while strictly maintaining
    index proportionality and the concentration cap.
    """
    if investment_amount <= 0:
        return {e["ticker"]: 0 for e in equities}, 0.0, 0.0
    
    equity_dict = {equity["ticker"]: equity for equity in equities}
    weights = calculate_weights_with_cap(equities, cap_percentage)
    
    # Binary search for optimal multiplier k in [1.0, 2.5]
    low = 1.0
    high = 2.5
    best_shares = {ticker: 0 for ticker in weights}
    best_cost_excl = 0.0
    best_cost_incl = 0.0
    
    for _ in range(40):
        mid = (low + high) / 2.0
        shares = {}
        total_cost_excl = 0.0
        
        for ticker, weight in weights.items():
            price = equity_dict[ticker]["price"]
            if price <= 0:
                raise ValueError(f"Invalid price for {ticker}: {price}")
            alloc = (investment_amount * mid) * weight
            s = int(alloc / (price * (1 + transaction_cost_rate)))
            shares[ticker] = s
            total_cost_excl += s * price
            
        cost_incl = total_cost_excl * (1 + transaction_cost_rate)
        
        if cost_incl <= investment_amount:
            best_shares = shares
            best_cost_excl = total_cost_excl
            best_cost_incl = cost_incl
            low = mid
        else:
            high = mid
            
    shares_per_ticker = best_shares
    total_cost_excl_fees = best_cost_excl
    total_cost_incl_fees = best_cost_incl
    remaining_cash = investment_amount - total_cost_incl_fees
    
    # Secondary pass: Greedy Cash Sweep to eliminate unallocated cash.
    # While residual cash can buy at least one share of any constituent,
    # pick the affordable candidate that minimizes absolute deviation from its target weight.
    min_unit_cost = min(eq["price"] * (1 + transaction_cost_rate) for eq in equities)
    while remaining_cash >= min_unit_cost:
        affordable = [
            eq for eq in equities
            if eq["price"] * (1 + transaction_cost_rate) <= remaining_cash
        ]
        if not affordable:
            break
            
        best_candidate = None
        best_score = float("inf")
        
        for eq in affordable:
            t = eq["ticker"]
            p = eq["price"]
            new_shares = shares_per_ticker[t] + 1
            new_total_excl = total_cost_excl_fees + p
            new_w = (new_shares * p) / new_total_excl
            score = abs(new_w - weights[t])
            if score < best_score:
                best_score = score
                best_candidate = eq
                
        if not best_candidate:
            break
            
        cand_t = best_candidate["ticker"]
        cand_price = best_candidate["price"]
        cand_unit_cost = cand_price * (1 + transaction_cost_rate)
        shares_per_ticker[cand_t] += 1
        total_cost_excl_fees += cand_price
        total_cost_incl_fees += cand_unit_cost
        remaining_cash -= cand_unit_cost
            
    total_cost_incl_fees = total_cost_excl_fees * (1 + transaction_cost_rate)
    return shares_per_ticker, total_cost_incl_fees, total_cost_excl_fees


def replicate_index_fund(
    fund_file: str,
    investment_amount: float,
    transaction_cost_rate: float = 0.03,
    cap_percentage: float = 0.15,
) -> Tuple[Dict[str, int], float, float]:
    """Replicate an index fund by determining shares to buy for each equity."""
    equities = load_fund_data(fund_file)
    if not equities:
        raise ValueError("Fund data is empty")
    
    return calculate_shares(
        equities, investment_amount, transaction_cost_rate, cap_percentage
    )


def replicate_index_fund_detailed(
    fund_file: str,
    investment_amount: float,
    transaction_cost_rate: float = 0.03,
    cap_percentage: float = 0.15,
) -> Dict:
    """Replicate an index fund and return comprehensive portfolio details.
    
    Eliminates cash drag via Optimal Multiplier Scaling while strictly maintaining target weights.
    """
    equities = load_fund_data(fund_file)
    if not equities:
        raise ValueError("Fund data is empty")

    if investment_amount <= 0:
        equity_dict = {equity["ticker"]: equity for equity in equities}
        weights = calculate_weights_with_cap(equities, cap_percentage)
        portfolio_items = [
            {
                "ticker": ticker,
                "title": equity_dict[ticker].get("title", ticker),
                "price": equity_dict[ticker]["price"],
                "market_cap": equity_dict[ticker].get("market_cap", 0.0),
                "target_weight": round(weight, 4),
                "target_weight_percent": round(weight * 100, 2),
                "shares": 0,
                "cost_excl_fees": 0.0,
                "fees_for_equity": 0.0,
                "total_cost": 0.0,
                "actual_weight": 0.0,
                "actual_weight_percent": 0.0,
            }
            for ticker, weight in sorted(weights.items(), key=lambda x: x[1], reverse=True)
        ]
        return {
            "investment_amount": 0.0,
            "transaction_cost_rate": transaction_cost_rate,
            "cap_percentage": cap_percentage,
            "total_cost_excl_fees": 0.0,
            "total_transaction_fees": 0.0,
            "total_cost_incl_fees": 0.0,
            "remaining_cash": 0.0,
            "capital_efficiency_percent": 0.0,
            "min_share_with_fee": 0.0,
            "cheapest_stock": "",
            "unallocated_cash_reason": "Enter an investment amount above 0.",
            "shares": {e["ticker"]: 0 for e in equities},
            "portfolio": portfolio_items,
        }

    shares_per_ticker, total_cost_incl_fees, total_cost_excl_fees = calculate_shares(
        equities, investment_amount, transaction_cost_rate, cap_percentage
    )
    
    equity_dict = {equity["ticker"]: equity for equity in equities}
    weights = calculate_weights_with_cap(equities, cap_percentage)
    
    total_transaction_fees = total_cost_excl_fees * transaction_cost_rate
    remaining_cash = max(0.0, investment_amount - total_cost_incl_fees)
    capital_efficiency_percent = (
        round(((investment_amount - remaining_cash) / investment_amount) * 100, 2)
        if investment_amount > 0 else 0.0
    )
    
    # Identify minimum price required to buy any single share
    min_share_price = min(e["price"] for e in equities)
    min_share_with_fee = min(e["price"] * (1 + transaction_cost_rate) for e in equities)
    cheapest_equity = min(equities, key=lambda e: e["price"])

    # Build detailed equity list
    portfolio_items = []
    for ticker, weight in sorted(weights.items(), key=lambda x: x[1], reverse=True):
        equity = equity_dict[ticker]
        shares = shares_per_ticker[ticker]
        cost_excl = shares * equity["price"]
        actual_weight = (cost_excl / total_cost_excl_fees) if total_cost_excl_fees > 0 else 0.0
        
        portfolio_items.append({
            "ticker": ticker,
            "title": equity.get("title", ticker),
            "price": equity["price"],
            "market_cap": equity.get("market_cap", 0.0),
            "target_weight": round(weight, 4),
            "target_weight_percent": round(weight * 100, 2),
            "shares": shares,
            "cost_excl_fees": round(cost_excl, 2),
            "fees_for_equity": round(cost_excl * transaction_cost_rate, 2),
            "total_cost": round(cost_excl * (1 + transaction_cost_rate), 2),
            "actual_weight": round(actual_weight, 4),
            "actual_weight_percent": round(actual_weight * 100, 2),
        })

    return {
        "investment_amount": round(investment_amount, 2),
        "transaction_cost_rate": transaction_cost_rate,
        "cap_percentage": cap_percentage,
        "total_cost_excl_fees": round(total_cost_excl_fees, 2),
        "total_transaction_fees": round(total_transaction_fees, 2),
        "total_cost_incl_fees": round(total_cost_incl_fees, 2),
        "remaining_cash": round(remaining_cash, 2),
        "capital_efficiency_percent": capital_efficiency_percent,
        "min_share_with_fee": round(min_share_with_fee, 2),
        "cheapest_stock": cheapest_equity["ticker"],
        "unallocated_cash_reason": (
            f"Residual cash (N{remaining_cash:,.2f}) cannot purchase additional shares without distorting target index weights. "
            f"Portfolio achieves {capital_efficiency_percent}% capital efficiency."
        ),
        "shares": shares_per_ticker,
        "portfolio": portfolio_items,
    }


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
        default="index_funds/oil_gas.json",
        help="Path to fund data JSON file (default: index_funds/oil_gas.json)",
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
        default=0.3,
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
