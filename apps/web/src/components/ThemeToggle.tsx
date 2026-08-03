"use client";

import { useEffect, useState } from "react";

/**
 * Light/dark toggle.
 *
 * The choice is stored so it survives navigation — a toggle that silently reset
 * on every link would read as a bug rather than as a preference.
 *
 * Every `localStorage` call is guarded, reads included. Blocked cookies and some
 * private-browsing modes make `localStorage` throw on *access*, not just on
 * write, and an unguarded read here runs inside the page's load path where one
 * throw takes down everything after it.
 */

export const THEME_STORAGE_KEY = "helios-theme";

export type Theme = "light" | "dark";

export function readStoredTheme(): Theme | null {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "dark" || stored === "light" ? stored : null;
  } catch {
    return null;
  }
}

export function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

/**
 * Applied before first paint via an inline script in the document head.
 *
 * This cannot be done in React. The site is a static export, so there is no
 * server to read the preference and no opportunity to set the attribute during
 * render; by the time a `useEffect` runs, the ivory ground has already painted
 * and a dark-mode reader has seen it flash.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});if(t==="dark"||t==="light"){document.documentElement.dataset.theme=t}}catch(e){}})();`;

/**
 * The active theme, for marks that cannot resolve a CSS custom property.
 *
 * MapLibre paint expressions take literal colour values, not `var()`, so the map
 * has to be handed real hex and told when it changes.
 */
export function useTheme(): Theme {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const resolve = () =>
      readStoredTheme() ?? (systemPrefersDark() ? "dark" : "light");

    setTheme(resolve());

    const onToggle = (event: Event) => {
      setTheme((event as CustomEvent<Theme>).detail);
    };
    // A reader who never touches the toggle still follows the OS, so the system
    // preference has to be watched too, not just our own event.
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onSystem = () => {
      if (readStoredTheme() === null) setTheme(resolve());
    };

    window.addEventListener("helios:themechange", onToggle);
    media?.addEventListener("change", onSystem);
    return () => {
      window.removeEventListener("helios:themechange", onToggle);
      media?.removeEventListener("change", onSystem);
    };
  }, []);

  return theme;
}

export function ThemeToggle() {
  // Null until mounted. The first render must match the prerendered HTML exactly
  // or hydration fails, and the prerender has no way to know the reader's theme.
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(readStoredTheme() ?? (systemPrefersDark() ? "dark" : "light"));
  }, []);

  function flip() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // The preference just won't outlive the session.
    }
    // Marks that resolve their colour from the surface — the map basemap, chiefly
    // — cannot observe a CSS custom property change, so they are told directly.
    window.dispatchEvent(
      new CustomEvent("helios:themechange", { detail: next }),
    );
  }

  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={flip}
      aria-label={`Switch to ${next} theme`}
    >
      {next === "dark" ? "Dark" : "Light"}
    </button>
  );
}
