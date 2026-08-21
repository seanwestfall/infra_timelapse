import assert from "node:assert/strict";
import { filterTargetsByTheme, inventoryTheme } from "../web/public/dashboard-theme.js";

const targets = [
  { id: "lahaina", type: "recovery_area", theme: "reconstruction" },
  { id: "legacy-port", type: "seaport" },
  { id: "legacy-waypoint", type: "corridor_waypoint" },
];

assert.equal(inventoryTheme(targets[0]), "reconstruction");
assert.equal(inventoryTheme(targets[1]), "ciit");
assert.equal(inventoryTheme(targets[2]), "bri");
assert.deepEqual(
  filterTargetsByTheme(targets, "reconstruction").map(({ id }) => id),
  ["lahaina"],
);
assert.deepEqual(filterTargetsByTheme(targets, "bri").map(({ id }) => id), ["legacy-waypoint"]);
assert.deepEqual(filterTargetsByTheme(targets, "ciit").map(({ id }) => id), ["legacy-port"]);
