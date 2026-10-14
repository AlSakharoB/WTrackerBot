import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomSheet, ConfirmDialog, FormField, ProgressBar, ToastProvider, useToast } from ".";

function ToastTrigger() {
  const { showToast } = useToast();
  return <button type="button" onClick={() => showToast(`Notice ${Date.now()}`)}>Notify</button>;
}

describe("shared UI components", () => {
  afterEach(() => vi.useRealTimers());
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

  it.each(["sheet", "dialog"])("consumes the complete backdrop click before closing a %s", (kind) => {
    const onBackgroundClick = vi.fn();
    const onClose = vi.fn();
    function Modal() {
      const [open, setOpen] = useState(true);
      const close = () => { onClose(); setOpen(false); };
      return (
        <div onClick={onBackgroundClick}>
          <button type="button" onClick={onBackgroundClick}>Background action</button>
          {kind === "sheet" ? (
            <BottomSheet open={open} title="Menu" onClose={close}><button>Inside menu</button></BottomSheet>
          ) : (
            <ConfirmDialog open={open} title="Menu" description="Confirm" onClose={close} onConfirm={vi.fn()} />
          )}
        </div>
      );
    }
    render(<Modal />);
    const backdrop = document.querySelector(kind === "sheet" ? ".sheet-backdrop" : ".dialog-backdrop")!;

    fireEvent.pointerDown(backdrop);
    expect(onClose).not.toHaveBeenCalled();
    expect(backdrop).toBeInTheDocument();
    fireEvent.pointerUp(backdrop);
    fireEvent.click(backdrop, { detail: 1 });

    expect(onClose).toHaveBeenCalledOnce();
    expect(backdrop).not.toBeInTheDocument();
    expect(onBackgroundClick).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Background action" }));
    expect(onBackgroundClick).toHaveBeenCalled();
  });

  it("does not close a sheet when a drag starts inside it and ends on the backdrop", () => {
    const onClose = vi.fn();
    render(<BottomSheet open title="Menu" onClose={onClose}><button>Inside menu</button></BottomSheet>);
    const backdrop = document.querySelector(".sheet-backdrop")!;
    fireEvent.pointerDown(screen.getByRole("button", { name: "Inside menu" }));
    fireEvent.pointerUp(backdrop);
    fireEvent.click(backdrop, { detail: 1 });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows at most two toasts and replaces older notices after their exit", () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    render(<ToastProvider><ToastTrigger /></ToastProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Notify" }));
    act(() => vi.advanceTimersByTime(10));
    fireEvent.click(screen.getByRole("button", { name: "Notify" }));
    act(() => vi.advanceTimersByTime(10));
    fireEvent.click(screen.getByRole("button", { name: "Notify" }));
    act(() => vi.advanceTimersByTime(10));
    fireEvent.click(screen.getByRole("button", { name: "Notify" }));

    expect(document.querySelectorAll(".toast")).toHaveLength(2);
    expect(document.querySelectorAll(".toast.is-leaving")).toHaveLength(2);
    act(() => vi.advanceTimersByTime(180));
    expect(document.querySelectorAll(".toast")).toHaveLength(2);
    expect(screen.queryByText("Notice 0")).not.toBeInTheDocument();
    expect(screen.queryByText("Notice 10")).not.toBeInTheDocument();
    expect(screen.getByText("Notice 20")).toBeInTheDocument();
    expect(screen.getByText("Notice 30")).toBeInTheDocument();
  });

  it("animates toast dismissal after two seconds and cleans up timers", () => {
    vi.useFakeTimers();
    const { unmount } = render(<ToastProvider><ToastTrigger /></ToastProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Notify" }));
    act(() => vi.advanceTimersByTime(2000));
    expect(document.querySelector(".toast")).toHaveClass("is-leaving");
    act(() => vi.advanceTimersByTime(180));
    expect(document.querySelector(".toast")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Notify" }));
    fireEvent.click(screen.getByRole("button", { name: "Скрыть уведомление" }));
    expect(document.querySelector(".toast")).toHaveClass("is-leaving");
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
