/**
 * Light / Dark / System theme choice.
 *
 * The choice is stored as data-theme on <html>; styles.css does the rest:
 * - "light": light colours (also the default, and what the page shows before
 *   any script has run, so there is no flash of dark colours).
 * - "dark": dark colours.
 * - "system": follows the operating system (prefers-color-scheme).
 *
 * The choice is remembered in localStorage when the browser allows it. Every
 * storage access is wrapped in try/catch: in a private window, with storage
 * blocked, or inside some embedded previews, even reading `window.localStorage`
 * throws. The page then simply uses the default and keeps working.
 */

export type ThemeChoice = "light" | "dark" | "system";

export const THEME_CHOICES: ThemeChoice[] = ["light", "dark", "system"];
export const DEFAULT_THEME: ThemeChoice = "light";
export const THEME_STORAGE_KEY = "lead-agent-dashboard:theme";

type StorageLike = Pick<Storage, "getItem" | "setItem">;
export type StorageGetter = () => StorageLike | null;

/** The browser's localStorage, or null when it is unavailable. */
export const browserStorage: StorageGetter = () => {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
};

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return typeof value === "string" && (THEME_CHOICES as string[]).includes(value);
}

/** The saved choice, or the default when nothing valid is saved or storage fails. */
export function readThemeChoice(getStorage: StorageGetter = browserStorage): ThemeChoice {
  try {
    const saved = getStorage()?.getItem(THEME_STORAGE_KEY);
    return isThemeChoice(saved) ? saved : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

/** Remember the choice. Returns false when it could not be saved; that is not an error. */
export function saveThemeChoice(
  choice: ThemeChoice,
  getStorage: StorageGetter = browserStorage,
): boolean {
  try {
    const storage = getStorage();
    if (!storage) return false;
    storage.setItem(THEME_STORAGE_KEY, choice);
    return true;
  } catch {
    return false;
  }
}

/** Put the choice on <html> so the matching colours in styles.css apply. */
export function applyThemeChoice(
  choice: ThemeChoice,
  root: { dataset: DOMStringMap } = document.documentElement,
): void {
  root.dataset.theme = choice;
}
