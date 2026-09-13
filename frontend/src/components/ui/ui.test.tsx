import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BottomSheet, ConfirmDialog, FormField, ProgressBar } from ".";

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

  it("locks the page and restores focus around a bottom sheet", async () => {
    const appRoot = document.createElement("div");
    appRoot.id = "root";
    document.body.append(appRoot);
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();
    const { rerender } = render(
      <BottomSheet open title="Редактор" onClose={vi.fn()}>
        <button type="button">Сохранить</button>
      </BottomSheet>,
    );

    await waitFor(() => expect(document.body).toHaveAttribute("data-overlay-open"));
    expect(document.getElementById("root")).toHaveProperty("inert", true);
    expect(screen.getByRole("dialog", { name: "Редактор" })).toContainElement(document.activeElement as HTMLElement);

    rerender(
      <BottomSheet open={false} title="Редактор" onClose={vi.fn()}>
        <button type="button">Сохранить</button>
      </BottomSheet>,
    );
    await waitFor(() => expect(document.body).not.toHaveAttribute("data-overlay-open"));
    expect(document.getElementById("root")).toHaveProperty("inert", false);
    expect(trigger).toHaveFocus();
    trigger.remove();
    appRoot.remove();
  });

  it("keeps keyboard focus inside a confirmation dialog", async () => {
    render(
      <ConfirmDialog
        open
        title="Удалить запись?"
        description="Действие нельзя отменить."
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const cancel = screen.getByRole("button", { name: "Отмена" });
    const confirm = screen.getByRole("button", { name: "Подтвердить" });
    await waitFor(() => expect(cancel).toHaveFocus());
    confirm.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(cancel).toHaveFocus();
    cancel.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();
  });
});
