from datetime import date
import unittest

from tradingbot.data_ingest.screener_adapter.fallback_parser import ScreenerFallbackParser


SAMPLE_HTML = """
<html>
  <body>
    <section id="analysis">
      <div class="pros"><ul><li>Healthy margin profile</li></ul></div>
      <div class="cons"><ul><li>Rich valuation</li></ul></div>
    </section>
    <section id="shareholding">
      <table class="data-table">
        <thead><tr><th>Shareholder</th><th>Mar 2024</th><th>Mar 2025</th></tr></thead>
        <tbody>
          <tr><td>Promoters</td><td>71%</td><td>72%</td></tr>
          <tr><td>FIIs</td><td>10%</td><td>9%</td></tr>
        </tbody>
      </table>
    </section>
    <section id="ratios">
      <table class="data-table">
        <thead><tr><th>Ratio</th><th>Mar 2024</th><th>Mar 2025</th></tr></thead>
        <tbody>
          <tr><td>ROCE %</td><td>26%</td><td>29%</td></tr>
        </tbody>
      </table>
    </section>
    <section id="balance-sheet">
      <table class="data-table">
        <thead><tr><th>Item</th><th>Mar 2024</th><th>Mar 2025</th></tr></thead>
        <tbody>
          <tr><td>Borrowings</td><td>10</td><td>8</td></tr>
          <tr><td>Equity Capital</td><td>20</td><td>20</td></tr>
        </tbody>
      </table>
    </section>
    <section id="cash-flow">
      <table class="data-table">
        <thead><tr><th>Item</th><th>Mar 2024</th><th>Mar 2025</th></tr></thead>
        <tbody>
          <tr><td>Cash from Operating Activity</td><td>100</td><td>110</td></tr>
        </tbody>
      </table>
    </section>
    <section id="profit-loss">
      <table class="ranges-table">
        <tbody>
          <tr><th>Compounded Sales Growth</th></tr>
          <tr><td>1 Year:</td><td>12%</td></tr>
          <tr><td>3 Years:</td><td>10%</td></tr>
        </tbody>
      </table>
      <table class="ranges-table">
        <tbody>
          <tr><th>Compounded Profit Growth</th></tr>
          <tr><td>1 Year:</td><td>14%</td></tr>
        </tbody>
      </table>
      <table class="ranges-table">
        <tbody>
          <tr><th>Return on Equity</th></tr>
          <tr><td>3 Years:</td><td>18%</td></tr>
        </tbody>
      </table>
    </section>
  </body>
</html>
"""


class ScreenerHistoryTest(unittest.TestCase):
    def test_parser_normalizes_historical_points(self) -> None:
        parser = ScreenerFallbackParser()
        history = parser.parse_history_from_html("HAL", SAMPLE_HTML)

        self.assertEqual(history.symbol, "HAL")
        self.assertEqual(len(history.shareholding_points), 4)
        self.assertEqual(history.shareholding_points[0].period_end, date(2024, 3, 31))
        self.assertEqual(history.shareholding_points[-1].metric_name, "FIIs")
        self.assertEqual(history.fundamental_points[0].availability_assumption, "annual_report_plus_90d")
        self.assertIn("Compounded Sales Growth", history.static_metrics)
