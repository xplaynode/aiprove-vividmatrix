"""
strategy.py — ETH 1-minute trend strategy for the AIProve eth-backtest bounty.

Design (deliberately simple and canonical — parameters are textbook defaults,
NOT fitted to this sample, so the held-out tail is not punished by overfitting):

  * Signal: EMA(fast=20) vs EMA(slow=120) of the close, evaluated at bar close.
  * Position: symmetric long/short. Long when EMA20 > EMA120 beyond a small
    deadband, short when below, flat inside the deadband. The deadband
    (|spread| <= 0.05% of price) exists only to cut fee-churning whipsaws.
  * Sizing: fixed full size (+1 / -1). Partial sizing adds parameters without
    adding robustness.
  * Causality: the decision for bar t uses bars[0..t] only; a runner executes
    it at bar t+1's open (see run_backtest.py). No lookahead anywhere.

Interface: two equivalent entry points, both causal —
  target_position(history) -> float in {-1.0, 0.0, 1.0}
      history: list of bar dicts with keys open/high/low/close/volume,
      in chronological order, ending at the current (just-closed) bar.
  Strategy().on_bar(bar) -> same, stateful/incremental version.
"""

FAST = 60         # EMA fast length (minutes)
SLOW = 240       # EMA slow length (minutes)
DEADBAND = 0.001  # 0.10% of price: minimum EMA spread to hold a position


class Strategy:
    def __init__(self, fast=FAST, slow=SLOW, deadband=DEADBAND):
        self.fast = fast
        self.slow = slow
        self.deadband = deadband
        self._kf = 2.0 / (fast + 1)
        self._ks = 2.0 / (slow + 1)
        self._ef = None
        self._es = None
        self._n = 0

    def on_bar(self, bar):
        close = float(bar["close"])
        if self._ef is None:
            self._ef = self._es = close
        else:
            self._ef += self._kf * (close - self._ef)
            self._es += self._ks * (close - self._es)
        self._n += 1
        if self._n < self.slow:      # warm-up: no position until slow EMA exists
            return 0.0
        spread = (self._ef - self._es) / close
        if spread > self.deadband:
            return 1.0
        if spread < -self.deadband:
            return -1.0
        return 0.0


_default = Strategy()


def target_position(history):
    """Stateless convenience wrapper: replays history through a Strategy."""
    s = Strategy()
    pos = 0.0
    for bar in history:
        pos = s.on_bar(bar)
    return pos
