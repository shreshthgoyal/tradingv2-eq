import unittest

from tradingbot.core.enums import RegimeLabel
from tradingbot.core.models import RegimeInput
from tradingbot.regime.engine import RegimeEngine


class RegimeTest(unittest.TestCase):
    def test_bull_trending_classification(self) -> None:
        engine = RegimeEngine()
        regime = engine.classify(
            RegimeInput(
                benchmark_above_200dma=True,
                benchmark_trend_strength=0.8,
                breadth_strength=0.7,
                vix_level=14.0,
                sector_strength=0.6,
                flow_strength=0.5,
            )
        )
        self.assertEqual(regime.label, RegimeLabel.BULL_TRENDING)
        self.assertGreater(regime.confidence, 0.5)
