import { ScreenerScraperPro } from "screener-scraper-pro";

const symbol = process.argv[2];
const historyMode = process.argv.includes("--history");
if (!symbol) {
  console.error("symbol argument is required");
  process.exit(1);
}

const url = `https://www.screener.in/company/${symbol}/`;
const data = await ScreenerScraperPro(url);
if (historyMode) {
  process.stdout.write(JSON.stringify({ url, data }));
  process.exit(0);
}
const latestQuarter = data?.quarters?.headers?.at(-1);
const latestProfitLossYear = data?.profitLoss?.headers?.at(-1);
const latestRatioYear = data?.ratios?.headers?.at(-1);
const latestShareholdingQuarter = data?.shareholding?.headers?.at(-1);

const response = {
  analysis: data.analysis ?? { pros: [], cons: [] },
  shareholding: Object.fromEntries(
    Object.entries(data.shareholding?.data ?? {}).map(([key, values]) => [
      key,
      parseFloat(String(values?.[latestShareholdingQuarter] ?? 0).replace("%", "")),
    ]),
  ),
  salesGrowthYoY: parseFloat(String(data.CAGRs?.["Compounded Sales Growth"]?.["1 Year"] ?? 0).replace("%", "")),
  profitGrowthYoY: parseFloat(String(data.CAGRs?.["Compounded Profit Growth"]?.["1 Year"] ?? 0).replace("%", "")),
  operatingCashflowTrend: Number(data.cashFlow?.data?.["Cash from Operating Activity"]?.[latestProfitLossYear] ?? 0),
  roce: parseFloat(String(data.ratios?.data?.["ROCE %"]?.[latestRatioYear] ?? 0).replace("%", "")),
  roe: parseFloat(String(data.CAGRs?.["Return on Equity"]?.["3 Years"] ?? 0).replace("%", "")),
  debtToEquity: Number(data.balanceSheet?.data?.["Borrowings"]?.[latestProfitLossYear] ?? 0) > 0
    ? Number(data.balanceSheet?.data?.["Borrowings"]?.[latestProfitLossYear] ?? 0) /
      Math.max(Number(data.balanceSheet?.data?.["Equity Capital"]?.[latestProfitLossYear] ?? 1), 1)
    : 0,
  pledgedPercentage: 0,
  latestQuarter,
};

process.stdout.write(JSON.stringify(response));
