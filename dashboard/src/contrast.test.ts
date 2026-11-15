import { describe, expect, it } from "vitest";
import { DECORATIVE, PAIRS, contrastRatio, luminance, themeTokens } from "./contrast";
import css from "./styles.css?raw";

const themes = themeTokens(css);

function rows(tokens: Record<string, string>, pairs = PAIRS) {
  return pairs.map((pair) => {
    const ratio = contrastRatio(tokens[pair.fg] ?? "#000", tokens[pair.bg] ?? "#000");
    const name = `${pair.fg} on ${pair.bg} = ${ratio.toFixed(2)}:1 (needs ${pair.min}) - ${pair.use}`;
    return { name, pair, ratio };
  });
}

describe.each([
  ["light", themes.light],
  ["dark", themes.dark],
])("%s theme meets WCAG AA", (_theme, tokens) => {
  it.each(rows(tokens).map((row) => [row.name, row]))("%s", (_name, row) => {
    expect(tokens[row.pair.fg], `--${row.pair.fg} is missing`).toBeDefined();
    expect(tokens[row.pair.bg], `--${row.pair.bg} is missing`).toBeDefined();
    expect(row.ratio).toBeGreaterThanOrEqual(row.pair.min);
  });

  it.each(rows(tokens, DECORATIVE).map((row) => [`decorative, not enforced: ${row.name}`, row]))(
    "%s",
    (_name, row) => {
      expect(Number.isFinite(row.ratio)).toBe(true);
    },
  );
});

describe("theme tokens", () => {
  it("defines the same tokens in light and dark", () => {
    expect(Object.keys(themes.dark).sort()).toEqual(Object.keys(themes.light).sort());
    expect(Object.keys(themes.light).length).toBeGreaterThan(40);
  });

  it("uses the dark colours for System when the computer is in dark mode", () => {
    expect(themes.systemDark).toEqual(themes.dark);
  });

  it("loads nothing from other sites", () => {
    expect(css).not.toMatch(/@import|url\(/i);
  });

  it("computes ratios like the WCAG reference values", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
    expect(luminance("#fff")).toBeCloseTo(1, 5);
  });
});
