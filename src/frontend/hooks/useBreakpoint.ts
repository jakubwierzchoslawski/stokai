import { useEffect, useState } from "react";

export const BREAKPOINTS = { sm: 375, md: 768, lg: 1280, xl: 1440 } as const;
export type Breakpoint = keyof typeof BREAKPOINTS;

export function useBreakpoint(): Breakpoint {
  const [bp, setBp] = useState<Breakpoint>(() => compute(window.innerWidth));
  useEffect(() => {
    const onResize = () => setBp(compute(window.innerWidth));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return bp;
}

function compute(w: number): Breakpoint {
  if (w >= BREAKPOINTS.xl) return "xl";
  if (w >= BREAKPOINTS.lg) return "lg";
  if (w >= BREAKPOINTS.md) return "md";
  return "sm";
}
