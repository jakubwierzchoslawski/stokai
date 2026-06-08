import js from "@eslint/js";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import a11y from "eslint-plugin-jsx-a11y";

export default [
  { ignores: ["dist/**", "node_modules/**", "coverage/**"] },

  // Base JS
  js.configs.recommended,

  // TypeScript source files
  {
    files: ["src/frontend/**/*.{ts,tsx}"],
    plugins: {
      "@typescript-eslint": tsPlugin,
      react: reactPlugin,
      "react-hooks": reactHooks,
      "jsx-a11y": a11y,
    },
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: "./tsconfig.json",
        ecmaFeatures: { jsx: true },
      },
    },
    settings: { react: { version: "detect" } },
    rules: {
      ...tsPlugin.configs["recommended"].rules,
      ...reactPlugin.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // No direct fetch against /api — use lib/api/client.ts
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='fetch'][arguments.0.type='Literal'][arguments.0.value=/^\\/api/]",
          message: "Direct fetch to /api is not allowed. Use the api() client from lib/api/client.ts.",
        },
      ],
      // No inline styles except in test files and legacy pages
      "react/forbid-component-props": [
        "warn",
        { forbid: [{ propName: "style", message: "Prefer Tailwind CSS classes over inline styles." }] },
      ],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-explicit-any": "warn",
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
    },
  },

  // Test files — relax some rules
  {
    files: ["**/*.test.{ts,tsx}", "tests/**/*.{ts,tsx}"],
    plugins: {
      "@typescript-eslint": tsPlugin,
    },
    languageOptions: {
      parser: tsParser,
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "no-restricted-syntax": "off",
      "react/forbid-component-props": "off",
    },
  },
];
