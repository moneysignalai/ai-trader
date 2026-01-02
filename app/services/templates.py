from app.services.setups.base import SignalCandidate


def trade_idea_with_options(signal: SignalCandidate, contract: dict) -> str:
    return (
        f"🚨 TRADE IDEA — {signal.ticker} {'CALLS' if signal.direction=='bull' else 'PUTS'}\n\n"
        f"I'm looking {'long' if signal.direction=='bull' else 'short'} {signal.ticker} here — {signal.reasons[0] if signal.reasons else 'clean look'}.\n\n"
        f"**How I'm playing it ({'CALLS' if signal.direction=='bull' else 'PUTS'}):**\n"
        f"- **Contract:** {contract.get('symbol', signal.ticker)} | Exp {contract.get('expiration','')}\n"
        f"- **Entry:** {signal.entry_trigger}\n"
        f"- **Stop:** {signal.stop}\n"
        f"- **Targets:** {signal.targets[0]} → {signal.targets[1]}\n\n"
        f"As long as price respects the plan, I'm staying with it."
    )


def trade_idea_stock_only(signal: SignalCandidate, reason: str) -> str:
    return (
        f"🚨 TRADE IDEA — {signal.ticker}\n\n"
        "I like this setup, but I'm not forcing options here — premium is priced too rich / liquidity isn't clean.\n\n"
        f"- **Entry:** {signal.entry_trigger}\n"
        f"- **Stop:** {signal.stop}\n"
        f"- **Targets:** {signal.targets[0]} → {signal.targets[1]}\n\n"
        f"{reason}"
    )


def im_in(trade) -> str:
    direction = "CALLS" if trade.direction == "bull" else "PUTS"
    return (
        f"✅ I'M IN — {trade.ticker} {direction}\n\n"
        f"I'm in {trade.ticker} now — trigger hit at {trade.entry_fill or trade.entry_trigger}.\n\n"
        f"- **Stop stays:** {trade.stop}\n"
        f"- **Next:** {trade.t1} first, then {trade.t2} if momentum holds."
    )


def im_out(trade) -> str:
    direction = "CALLS" if trade.direction == "bull" else "PUTS"
    reason = trade.exit_reason or "Plan closed"
    return f"🏁 I'M OUT — {trade.ticker} {direction}\n{reason}."
