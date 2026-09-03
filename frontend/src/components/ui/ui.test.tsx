import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog, FormField, ProgressBar } from ".";

describe("shared UI components", () => {
  it("clamps progress visually and for assistive technology", () => {
    render(<ProgressBar label="Белки" value={140} max={100} />);
    const progress = screen.getByRole("progressbar", { name: "Белки" });
    expect(progress).toHaveAttribute("aria-valuenow", "100");
    expect(progress.firstElementChild).toHaveStyle({ width: "100%" });
  });

  it("links form errors to their control", () => {
    render(
      <FormField label="Название" htmlFor="name" error="Введите название">
        <input id="name" />
      </FormField>,
    );
    expect(screen.getByLabelText("Название")).toHaveAttribute(
      "aria-describedby",
      "name-description",
    );
    expect(screen.getByLabelText("Название")).toHaveAttribute("aria-invalid", "true");
  });

  it("closes confirmation with Escape", () => {
    const onClose = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Удалить запись?"
        description="Действие нельзя отменить."
        onConfirm={vi.fn()}
        onClose={onClose}
      />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
