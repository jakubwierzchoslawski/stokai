/**
 * useBreakpoint.ts — Reactive breakpoint detection hook.
 *
 * Returns the current active breakpoint name derived from matchMedia queries
 * corresponding to the canonical Tailwind breakpoints:
 *
 *   sm  = viewport width < 768px
 *   md  = 768px ≤ width < 1280px
 *   lg  = 1280px ≤ width < 1440px
 *   xl  = width ≥ 1440px
 *
 * Registers three threshold media query listeners and updates on every resize
 * crossing. Cleans up all listeners on unmount. Safe in SSR environments.
 *
 * PLAN-N-014 TASK-002
 */

import { useState, useEffect } from "react";

export type Breakpoint = "sm" | "md" | "lg" | "xl";

const MD_QUERY = "(min-width: 768px)";
const LG_QUERY = "(min-width: 1280px)";
const XL_QUERY = "(min-width: 1440px)";

function deriveBreakpoint(md: boolean, lg: boolean, xl: boolean): Breakpoint {
  if (xl) return "xl";
  if (lg) return "lg";
  if (md) return "md";
  return "sm";
}

/**
 * Returns the current viewport breakpoint as a stable string.
 * Updates reactively on viewport resize crossing a threshold.
 */
export function useBreakpoint(): Breakpoint {
  // SSR guard: return 'sm' if running without window.
  const getInitial = (): Breakpoint => {
    if (typeof window === "undefined") return "sm";
    const md = window.matchMedia(MD_QUERY).matches;
    const lg = window.matchMedia(LG_QUERY).matches;
    const xl = window.matchMedia(XL_QUERY).matches;
    return deriveBreakpoint(md, lg, xl);
  };

  const [breakpoint, setBreakpoint] = useState<Breakpoint>(getInitial);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mdMql = window.matchMedia(MD_QUERY);
    const lgMql = window.matchMedia(LG_QUERY);
    const xlMql = window.matchMedia(XL_QUERY);

    const update = () => {
      setBreakpoint(deriveBreakpoint(mdMql.matches, lgMql.matches, xlMql.matches));
    };

    mdMql.addEventListener("change", update);
    lgMql.addEventListener("change", update);
    xlMql.addEventListener("change", update);

    return () => {
      mdMql.removeEventListener("change", update);
      lgMql.removeEventListener("change", update);
      xlMql.removeEventListener("change", update);
    };
  }, []);

  return breakpoint;
}
