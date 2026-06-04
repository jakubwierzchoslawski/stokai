/**
 * tailwind.config.ts — Canonical Tailwind CSS breakpoint configuration.
 *
 * Overrides Tailwind's default screens (sm=640px conflicts with 375px mobile-first
 * requirement) with four project-specific breakpoints that serve both layout strategies:
 *
 *   mobile-first  → base styles target sm (375px)
 *   desktop-first → base styles target lg (1280px); md collapses panels
 *
 * Export the screens record so TypeScript consumers can import breakpoint values
 * as constants without string duplication.
 *
 * PLAN-N-014 TASK-001
 */

import type { Config } from "tailwindcss";

/**
 * Canonical breakpoint values used project-wide.
 * Import in TypeScript code to avoid string duplication.
 */
export const SCREENS = {
  sm: "375px",
  md: "768px",
  lg: "1280px",
  xl: "1440px",
} as const;

export type ScreenKey = keyof typeof SCREENS;

const config: Config = {
  content: [
    "./src/frontend/**/*.{ts,tsx}",
    "./src/frontend/index.html",
  ],
  theme: {
    // Replace ALL default Tailwind screens with the four canonical breakpoints.
    // Tailwind's default sm=640px conflicts with the 375px mobile-first requirement.
    screens: SCREENS,
    extend: {},
  },
  plugins: [],
};

export default config;
