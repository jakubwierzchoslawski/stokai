/**
 * Tests for FormulaCanvas component.
 *
 * Verifies:
 * - Renders error annotations when validationResult.errors is non-empty
 * - Save button is disabled when there are errors
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { FormulaCanvas } from "../FormulaCanvas";

// Mock the useFormulaValidation hook
jest.mock("../hooks/useFormulaValidation", () => ({
  useFormulaValidation: jest.fn(),
}));

const { useFormulaValidation } = jest.requireMock("../hooks/useFormulaValidation");

describe("FormulaCanvas", () => {
  const defaultProps = {
    formula: "revenue * 0.5",
    onFormulaChange: jest.fn(),
    onSave: jest.fn(),
    isSaving: false,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders error annotations when validationResult has errors", () => {
    useFormulaValidation.mockReturnValue({
      validationResult: {
        valid: false,
        errors: ["Unknown parameter: foo", "Unknown parameter: bar"],
      },
      isValidating: false,
      validate: jest.fn(),
    });

    render(<FormulaCanvas {...defaultProps} formula="foo + bar" />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Unknown parameter: foo")).toBeInTheDocument();
    expect(screen.getByText("Unknown parameter: bar")).toBeInTheDocument();
  });

  it("does not show errors when formula is valid", () => {
    useFormulaValidation.mockReturnValue({
      validationResult: { valid: true, errors: [] },
      isValidating: false,
      validate: jest.fn(),
    });

    render(<FormulaCanvas {...defaultProps} />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Formula is valid")).toBeInTheDocument();
  });

  it("disables Save button when formula has errors", () => {
    useFormulaValidation.mockReturnValue({
      validationResult: {
        valid: false,
        errors: ["Unknown parameter: foo"],
      },
      isValidating: false,
      validate: jest.fn(),
    });

    render(<FormulaCanvas {...defaultProps} formula="foo" />);

    const saveButton = screen.getByRole("button", { name: /save indicator/i });
    expect(saveButton).toBeDisabled();
  });

  it("disables Save button when isSaving is true", () => {
    useFormulaValidation.mockReturnValue({
      validationResult: { valid: true, errors: [] },
      isValidating: false,
      validate: jest.fn(),
    });

    render(<FormulaCanvas {...defaultProps} isSaving={true} />);

    const saveButton = screen.getByRole("button");
    expect(saveButton).toBeDisabled();
  });

  it("shows validating indicator when isValidating is true", () => {
    useFormulaValidation.mockReturnValue({
      validationResult: null,
      isValidating: true,
      validate: jest.fn(),
    });

    render(<FormulaCanvas {...defaultProps} />);

    expect(screen.getByText("Validating...")).toBeInTheDocument();
  });
});
