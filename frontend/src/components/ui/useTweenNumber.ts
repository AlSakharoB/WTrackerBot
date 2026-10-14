import { animate, useMotionValue, useReducedMotion } from "motion/react";
import { useEffect } from "react";

export function useTweenNumber(value: number) {
  const current = useMotionValue(value);
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    if (reducedMotion) { current.set(value); return; }
    if (current.get() === value) return;
    const animation = animate(current, value, { duration: 0.42, ease: [0.22, 1, 0.36, 1] });
    return () => animation.stop();
  }, [current, reducedMotion, value]);
  return current;
}
