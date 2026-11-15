import { describe, expect, it } from "vitest";
import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  applyThemeChoice,
  isThemeChoice,
  readThemeChoice,
  saveThemeChoice,
} from "./theme";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
  };
}

const throwing = () => {
  throw new Error("storage blocked");
};

describe("theme choice", () => {
  it("defaults to light", () => {
    expect(DEFAULT_THEME).toBe("light");
    expect(readThemeChoice(() => memoryStorage())).toBe("light");
  });

  it("reads back a saved choice", () => {
    const storage = memoryStorage();
    expect(saveThemeChoice("dark", () => storage)).toBe(true);
    expect(storage.data.get(THEME_STORAGE_KEY)).toBe("dark");
    expect(readThemeChoice(() => storage)).toBe("dark");
    saveThemeChoice("system", () => storage);
    expect(readThemeChoice(() => storage)).toBe("system");
  });

  it("ignores a saved value that is not a valid choice", () => {
    expect(readThemeChoice(() => memoryStorage({ [THEME_STORAGE_KEY]: "purple" }))).toBe("light");
    expect(isThemeChoice("dark")).toBe(true);
    expect(isThemeChoice(null)).toBe(false);
  });

  it("keeps working when storage is missing or throws", () => {
    expect(readThemeChoice(() => null)).toBe("light");
    expect(saveThemeChoice("dark", () => null)).toBe(false);
    // reaching localStorage itself throws (blocked storage, some previews)
    expect(readThemeChoice(throwing)).toBe("light");
    expect(saveThemeChoice("dark", throwing)).toBe(false);
    // getItem / setItem throw (private mode, quota)
    const broken = { getItem: throwing, setItem: throwing };
    expect(readThemeChoice(() => broken)).toBe("light");
    expect(saveThemeChoice("dark", () => broken)).toBe(false);
  });

  it("puts the choice on the root element", () => {
    const root = { dataset: {} as DOMStringMap };
    applyThemeChoice("dark", root);
    expect(root.dataset.theme).toBe("dark");
  });
});
