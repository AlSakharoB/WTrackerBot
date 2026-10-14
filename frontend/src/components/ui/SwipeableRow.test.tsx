import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LONG_PRESS_MS, SwipeableRow } from "./SwipeableRow";

const edit = vi.fn();
const remove = vi.fn();
const hold = vi.fn();

function Harness({ disabled = false }: { disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  return <SwipeableRow label="Банан" open={open} onOpenChange={setOpen} onDelete={remove} onLongPress={hold} disabled={disabled}>
    <button onClick={edit}>Банан</button><button data-row-action>Папка</button>
  </SwipeableRow>;
}

const pointer = { pointerId: 1, isPrimary: true, pointerType: "touch", button: 0, clientX: 150, clientY: 50 };

describe("list gestures", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.stubGlobal("PointerEvent", class extends MouseEvent {
      pointerId: number;
      isPrimary: boolean;
      pointerType: string;
      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init);
        this.pointerId = init.pointerId ?? 1;
        this.isPrimary = init.isPrimary ?? true;
        this.pointerType = init.pointerType ?? "touch";
      }
    });
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("reveals delete on a left swipe without deleting or opening the item", () => {
    render(<Harness />);
    const item = screen.getByRole("button", { name: "Банан" });
    fireEvent.pointerDown(item, pointer);
    fireEvent.pointerMove(item, { ...pointer, clientX: 65 });
    fireEvent.pointerUp(item, { ...pointer, clientX: 65 });
    fireEvent.click(item, { detail: 1 });
    expect(document.querySelector(".swipe-row")).toHaveAttribute("data-open", "true");
    expect(edit).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Удалить Банан" }));
    expect(remove).toHaveBeenCalledOnce();
  });

  it("closes an open action on a tap without opening the editor underneath", () => {
    render(<Harness />);
    const item = screen.getByRole("button", { name: "Банан" });
    fireEvent.pointerDown(item, pointer);
    fireEvent.pointerMove(item, { ...pointer, clientX: 65 });
    fireEvent.pointerUp(item, pointer);
    fireEvent.click(item, { detail: 1 });
    fireEvent.pointerDown(item, pointer);
    fireEvent.pointerUp(item, pointer);
    fireEvent.click(item, { detail: 1 });
    expect(document.querySelector(".swipe-row")).toHaveAttribute("data-open", "false");
    expect(edit).not.toHaveBeenCalled();
    fireEvent.click(item);
    expect(edit).toHaveBeenCalledOnce();
  });

  it("keeps swiping when pointer capture moves from a nested element to the row", () => {
    render(<Harness />);
    const item = screen.getByRole("button", { name: "Банан" });
    fireEvent.pointerDown(item, pointer);
    fireEvent.pointerMove(item, { ...pointer, clientX: 135 });
    fireEvent.lostPointerCapture(item, { ...pointer, clientX: 130 });
    fireEvent.pointerMove(item, { ...pointer, clientX: 65 });
    fireEvent.pointerUp(item, { ...pointer, clientX: 65 });
    expect(document.querySelector(".swipe-row")).toHaveAttribute("data-open", "true");
    expect(remove).not.toHaveBeenCalled();
  });

  it("opens the editor once on a hold and consumes the generated click", () => {
    render(<Harness />);
    const item = screen.getByRole("button", { name: "Банан" });
    fireEvent.pointerDown(item, pointer);
    act(() => vi.advanceTimersByTime(LONG_PRESS_MS - 1));
    expect(hold).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    fireEvent.pointerUp(item, pointer);
    fireEvent.click(item, { detail: 1 });
    expect(hold).toHaveBeenCalledOnce();
    expect(edit).not.toHaveBeenCalled();
  });

  it.each(["vertical", "cancel", "secondary", "action", "unmount"])("cancels a hold for %s", (reason) => {
    const { unmount } = render(<Harness />);
    const item = screen.getByRole("button", { name: reason === "action" ? "Папка" : "Банан" });
    fireEvent.pointerDown(item, pointer);
    if (reason === "vertical") fireEvent.pointerMove(item, { ...pointer, clientY: 90 });
    if (reason === "cancel") fireEvent.pointerCancel(item, pointer);
    if (reason === "secondary") fireEvent.pointerDown(item, { ...pointer, pointerId: 2, isPrimary: false });
    if (reason === "unmount") unmount();
    act(() => vi.advanceTimersByTime(LONG_PRESS_MS));
    expect(hold).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });

  it("does not reveal delete for a short swipe or a cancelled pointer", () => {
    render(<Harness />);
    const item = screen.getByRole("button", { name: "Банан" });
    fireEvent.pointerDown(item, pointer);
    fireEvent.pointerMove(item, { ...pointer, clientX: 130 });
    fireEvent.pointerUp(item, pointer);
    expect(document.querySelector(".swipe-row")).toHaveAttribute("data-open", "false");
    fireEvent.pointerDown(item, pointer);
    fireEvent.pointerMove(item, { ...pointer, clientX: 65 });
    fireEvent.pointerCancel(item, pointer);
    expect(document.querySelector(".swipe-row")).toHaveAttribute("data-open", "false");
  });

  it("disables gestures while preserving ordinary item activation", () => {
    render(<Harness disabled />);
    const item = screen.getByRole("button", { name: "Банан" });
    fireEvent.pointerDown(item, pointer);
    fireEvent.pointerMove(item, { ...pointer, clientX: 65 });
    act(() => vi.advanceTimersByTime(LONG_PRESS_MS));
    fireEvent.pointerUp(item, pointer);
    fireEvent.click(item);
    expect(hold).not.toHaveBeenCalled();
    expect(edit).toHaveBeenCalledOnce();
    expect(document.querySelector(".swipe-row")).toHaveAttribute("data-open", "false");
  });
});
