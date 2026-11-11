// Run: node --test --experimental-strip-types web/lib/knapsack.test.ts   (Node ≥ 22.6)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { knapsackSelect, type KnapsackItem } from "./knapsack.ts";

interface Case {
  items: KnapsackItem[];
  budget: number;
  expected: { ids: string[]; value: number; hours: number };
}

const fixture = JSON.parse(
  readFileSync(new URL("./__fixtures__/knapsack_cases.json", import.meta.url), "utf8"),
) as { cases: Case[] };

test("matches the Python implementation on 1,000 random cases", () => {
  assert.equal(fixture.cases.length, 1000);
  for (const [k, c] of fixture.cases.entries()) {
    const r = knapsackSelect(c.items, c.budget);
    assert.deepEqual(r.ids, c.expected.ids, `case ${k}: ids`);
    assert.equal(r.hours, c.expected.hours, `case ${k}: hours`);
    assert.ok(Math.abs(r.value - c.expected.value) < 1e-9, `case ${k}: value`);
  }
});

test("never exceeds budget and rejects bad input", () => {
  const items = [
    { id: "a", value: 100, hours: 3 },
    { id: "b", value: 90, hours: 3 },
    { id: "c", value: 80, hours: 2 },
  ];
  for (let b = 0; b <= 9; b++) assert.ok(knapsackSelect(items, b).hours <= b);
  assert.throws(() => knapsackSelect(items, -1));
  assert.throws(() => knapsackSelect([{ id: "x", value: 1, hours: 0 }], 3));
});
