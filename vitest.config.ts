import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    root: ".",
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./tests/frontend/setupTests.ts"],
      include: [
        "src/frontend/**/*.{test,spec}.{ts,tsx}",
        "tests/frontend/**/*.{test,spec}.{ts,tsx}",
      ],
      exclude: ["node_modules", "dist"],
      css: false,
      coverage: {
        provider: "v8",
        reporter: ["text", "html"],
        include: ["src/frontend/**/*.{ts,tsx}"],
        exclude: [
          "src/frontend/**/*.{test,spec}.{ts,tsx}",
          "src/frontend/**/*.d.ts",
          "src/frontend/main.tsx",
          "src/frontend/ui/**",
        ],
      },
    },
  }),
);
