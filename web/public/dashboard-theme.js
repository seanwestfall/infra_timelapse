export const DASHBOARD_THEMES = Object.freeze({
  reconstruction: "Reconstruction",
  bri: "BRI",
  ciit: "CIIT",
});

export function inventoryTheme(target = {}) {
  if (target.theme) return String(target.theme).toLocaleLowerCase();
  // Compatibility defaults for inventory records created before themes.
  return target.type === "corridor_waypoint" ? "bri" : "ciit";
}

export function filterTargetsByTheme(targets, theme) {
  return targets.filter((target) => inventoryTheme(target) === theme);
}
