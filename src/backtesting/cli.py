"""CLI for running backtests."""
from __future__ import annotations

from src.backtesting.engine import BacktestEngine
from src.backtesting.metrics import compute_metrics, outcome_vector


def main() -> None:
    engine = BacktestEngine()
    results = engine.run(competition="FIFA World Cup", season="2022")

    if not results:
        print("No matches to backtest.")
        return

    predictions = [r.predicted_probs for r in results]
    outcomes = [
        outcome_vector(int(r.actual_score.split("-")[0]), int(r.actual_score.split("-")[1]))
        for r in results
    ]
    metrics = compute_metrics(predictions, outcomes)

    print(f"Backtested {metrics.n} matches")
    print(f"RPS:                 {metrics.rps:.4f}")
    print(f"Log-loss:            {metrics.log_loss:.4f}")
    print(f"Brier (win):         {metrics.brier:.4f}")
    print(f"Accuracy:            {metrics.accuracy:.3f}")
    print(f"Calibration error:   {metrics.calibration_error:.4f}")


if __name__ == "__main__":
    main()
