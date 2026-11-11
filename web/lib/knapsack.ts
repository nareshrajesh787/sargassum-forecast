/**
 * Exact 0/1 knapsack crew allocation, a line-for-line TypeScript port of decision/knapsack.py, which is
 * itself ported from `knapsack_select` in Costa (https://github.com/nareshrajesh787/Costa) by
 * nareshrajesh787 and Avisator1. Tested against the Python version on 1,000 random cases
 * (web/lib/knapsack.test.ts).
 */

export interface KnapsackItem {
  id: string;
  value: number;
  hours: number; // positive integer crew-hours
}

export interface KnapsackResult {
  ids: string[]; // selected ids in catalog order
  value: number;
  hours: number;
}

export function knapsackSelect(items: KnapsackItem[], budget: number): KnapsackResult {
  if (budget < 0) throw new Error("budget must be >= 0");
  if (budget === 0 || items.length === 0) return { ids: [], value: 0, hours: 0 };

  const n = items.length;
  const hoursList: number[] = [];
  const valueList: number[] = [];
  for (const item of items) {
    const h = Math.trunc(item.hours);
    if (h <= 0) throw new Error(`item ${item.id} has non-positive hours`);
    hoursList.push(h);
    valueList.push(Number(item.value));
  }

  // dp[i][w] = max value using the first i items with capacity w
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(budget + 1).fill(0));
  const take: boolean[][] = Array.from({ length: n + 1 }, () => new Array<boolean>(budget + 1).fill(false));

  for (let i = 1; i <= n; i++) {
    const h = hoursList[i - 1];
    const v = valueList[i - 1];
    for (let w = 0; w <= budget; w++) {
      dp[i][w] = dp[i - 1][w];
      take[i][w] = false;
      if (h <= w) {
        const candidate = dp[i - 1][w - h] + v;
        if (candidate > dp[i][w] + 1e-12) {
          dp[i][w] = candidate;
          take[i][w] = true;
        }
      }
    }
  }

  // smallest capacity that reaches the best value (Python: max over w of (dp[n][w], -w))
  let bestW = 0;
  for (let w = 1; w <= budget; w++) {
    if (dp[n][w] > dp[n][bestW]) bestW = w;
  }

  const selected: number[] = [];
  let w = bestW;
  for (let i = n; i >= 1; i--) {
    if (take[i][w]) {
      selected.push(i - 1);
      w -= hoursList[i - 1];
    }
  }
  selected.sort((a, b) => a - b);
  return {
    ids: selected.map((i) => items[i].id),
    value: selected.reduce((s, i) => s + valueList[i], 0),
    hours: selected.reduce((s, i) => s + hoursList[i], 0),
  };
}
