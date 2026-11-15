/**
 * WCAG contrast check for the colour tokens in styles.css.
 *
 * `npm run contrast` prints every pair with its ratio; `npm test` fails if any
 * pair is below its minimum. Minimums follow WCAG 2.x level AA:
 * 4.5:1 for normal text, 3:1 for large text, control borders, focus rings and
 * other graphics people need to see.
 */

export type Tokens = Record<string, string>;

export interface ContrastPair {
  fg: string;
  bg: string;
  min: number;
  use: string;
}

const TEXT = 4.5;
const UI = 3;

/** Every foreground/background pair the page actually uses. */
export const PAIRS: ContrastPair[] = [
  // Text
  { fg: "text", bg: "bg", min: TEXT, use: "body text on the page" },
  { fg: "text", bg: "surface", min: TEXT, use: "body text on cards" },
  { fg: "text-2", bg: "surface", min: TEXT, use: "secondary text, route labels" },
  { fg: "text-2", bg: "surface-2", min: TEXT, use: "table header text" },
  { fg: "muted", bg: "surface", min: TEXT, use: "hints and labels on cards" },
  { fg: "muted", bg: "bg", min: TEXT, use: "hints on the page" },
  { fg: "muted", bg: "surface-2", min: TEXT, use: "hints in boxes" },
  { fg: "text", bg: "surface-2", min: TEXT, use: "message and draft text" },
  { fg: "text", bg: "row-hover", min: TEXT, use: "text on a hovered row" },
  { fg: "muted", bg: "row-hover", min: TEXT, use: "sub text on a hovered row" },
  { fg: "text", bg: "accent-soft", min: TEXT, use: "text on the selected row" },
  { fg: "muted", bg: "accent-soft", min: TEXT, use: "sub text on the selected row" },
  { fg: "accent", bg: "surface", min: TEXT, use: "links and accent text" },
  { fg: "accent-text", bg: "accent", min: TEXT, use: "primary button, active toggle" },
  { fg: "accent-text", bg: "accent-hover", min: TEXT, use: "primary button on hover" },
  { fg: "info-fg", bg: "info-bg", min: TEXT, use: "demo banner" },
  // Badges (the text label is always shown, so colour is never the only cue)
  { fg: "green-fg", bg: "green-bg", min: TEXT, use: "Approved, Local mode" },
  { fg: "amber-fg", bg: "amber-bg", min: TEXT, use: "Awaiting approval, Demo data" },
  { fg: "red-fg", bg: "red-bg", min: TEXT, use: "Needs a human, handover reason" },
  { fg: "blue-fg", bg: "blue-bg", min: TEXT, use: "Nurture" },
  { fg: "grey-fg", bg: "grey-bg", min: TEXT, use: "Discarded, chips" },
  { fg: "rejected-fg", bg: "rejected-bg", min: TEXT, use: "Rejected" },
  { fg: "hot-fg", bg: "hot-bg", min: TEXT, use: "HOT badge" },
  { fg: "score-high-fg", bg: "score-high-bg", min: TEXT, use: "score chip 7-10" },
  { fg: "score-mid-fg", bg: "score-mid-bg", min: TEXT, use: "score chip 4-6" },
  { fg: "score-low-fg", bg: "score-low-bg", min: TEXT, use: "score chip 1-3" },
  // Controls and graphics
  { fg: "border-strong", bg: "surface", min: UI, use: "button and input borders" },
  { fg: "border-strong", bg: "surface-2", min: UI, use: "button borders in the action box" },
  { fg: "focus", bg: "surface", min: UI, use: "keyboard focus ring on cards" },
  { fg: "focus", bg: "bg", min: UI, use: "keyboard focus ring on the page" },
  { fg: "accent", bg: "accent-soft", min: UI, use: "selected-row marker bar" },
  { fg: "hot-bg", bg: "surface", min: UI, use: "HOT badge against the card" },
  { fg: "score-high-bg", bg: "surface", min: UI, use: "strong score chip against the card" },
  { fg: "dot-accent", bg: "surface", min: UI, use: "route dot: draft reply" },
  { fg: "dot-red", bg: "surface", min: UI, use: "route dot: handover" },
  { fg: "dot-blue", bg: "surface", min: UI, use: "route dot: nurture" },
  { fg: "dot-grey", bg: "surface", min: UI, use: "route dot: spam" },
  { fg: "bar-high", bg: "bar-track", min: UI, use: "score bar 7-10" },
  { fg: "bar-mid", bg: "bar-track", min: UI, use: "score bar 4-6" },
];

/**
 * Pairs that are decorative under WCAG 1.4.11 (card edges, row dividers, the
 * bar for low scores). Reported, never enforced.
 */
export const DECORATIVE: ContrastPair[] = [
  { fg: "border", bg: "surface", min: 0, use: "card edges and row dividers" },
  { fg: "surface", bg: "bg", min: 0, use: "card against the page" },
  { fg: "bar-low", bg: "bar-track", min: 0, use: "score bar 1-3 (deliberately muted)" },
];

/** The body of the first rule whose selector is exactly `selector`. */
export function cssBlock(css: string, selector: string): string {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`No "${selector}" block in styles.css`);
  const open = css.indexOf("{", start);
  return css.slice(open + 1, css.indexOf("}", open));
}

/** `--name: #hex;` declarations in a block. Other values (shadows) are ignored. */
export function parseTokens(block: string): Tokens {
  const tokens: Tokens = {};
  for (const match of block.matchAll(/--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;/g)) {
    tokens[match[1]] = match[2].toLowerCase();
  }
  return tokens;
}

export function themeTokens(css: string): { light: Tokens; dark: Tokens; systemDark: Tokens } {
  return {
    light: parseTokens(cssBlock(css, ":root")),
    dark: parseTokens(cssBlock(css, ':root[data-theme="dark"]')),
    systemDark: parseTokens(cssBlock(css, ':root[data-theme="system"]')),
  };
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  let digits = hex.replace("#", "");
  if (digits.length === 3) digits = [...digits].map((d) => d + d).join("");
  if (!/^[0-9a-fA-F]{6}$/.test(digits)) throw new Error(`Not a hex colour: ${hex}`);
  const [r, g, b] = [0, 2, 4].map((i) => channel(parseInt(digits.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
