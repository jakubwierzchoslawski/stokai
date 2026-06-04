/**
 * Jest configuration for frontend TypeScript/React tests.
 *
 * Test files live under tests/frontend/.
 * Uses ts-jest for TypeScript transformation and jsdom as the test environment.
 */
/** @type {import('jest').Config} */
module.exports = {
  displayName: "frontend",
  testEnvironment: "jsdom",
  testMatch: ["<rootDir>/tests/frontend/**/*.test.{ts,tsx}"],
  transform: {
    "^.+\\.(ts|tsx)$": [
      "ts-jest",
      {
        tsconfig: {
          jsx: "react-jsx",
          esModuleInterop: true,
          allowSyntheticDefaultImports: true,
          moduleResolution: "node",
          target: "ES2020",
          lib: ["ES2020", "DOM", "DOM.Iterable"],
          strict: false,
        },
      },
    ],
  },
  moduleNameMapper: {
    "\\.(css|less|scss|sass)$": "<rootDir>/tests/frontend/__mocks__/styleMock.js",
    "^dompurify$": "<rootDir>/tests/frontend/__mocks__/dompurify.js",
  },
  setupFilesAfterFramework: ["@testing-library/jest-dom/extend-expect"],
  setupFilesAfterEnv: ["<rootDir>/tests/frontend/setupTests.ts"],
};
