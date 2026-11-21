export type ThemeChoice = "dark" | "light" | "system";
export const THEME_KEY = "nexus-theme";

export function resolveTheme(choice: ThemeChoice, prefersDark: boolean): "dark" | "light" {
  if (choice === "system") return prefersDark ? "dark" : "light";
  return choice;
}

export function readThemeChoice(): ThemeChoice {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "system" || v === "dark" ? v : "dark";
  } catch {
    return "dark";
  }
}

export function applyTheme(choice: ThemeChoice) {
  try {
    localStorage.setItem(THEME_KEY, choice);
  } catch {
    /* storage can be unavailable; the theme still applies for this page view */
  }
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = resolveTheme(choice, prefersDark);
}

// Runs before first paint so the page never flashes the wrong theme. Dark is the default.
export const themeBootstrap = `(function(){try{var c=localStorage.getItem('${THEME_KEY}')||'dark';var d=c==='system'?matchMedia('(prefers-color-scheme: dark)').matches:c!=='light';document.documentElement.dataset.theme=d?'dark':'light'}catch(e){document.documentElement.dataset.theme='dark'}})();`;
