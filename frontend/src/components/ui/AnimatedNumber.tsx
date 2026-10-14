import { motion, useTransform } from "motion/react";
import { useMemo } from "react";

import type { NumberFormat } from "../../api/client";
import { useTweenNumber } from "./useTweenNumber";

export function AnimatedNumber({ value, format, energy = false, suffix = "" }: { value: number; format: NumberFormat; energy?: boolean; suffix?: string }) {
  const current = useTweenNumber(value);
  const formatter = useMemo(() => new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: format === "automatic" ? 0 : format === "one_decimal" ? 1 : 2,
    maximumFractionDigits: format === "one_decimal" ? 1 : 2,
  }), [format]);
  const text = useTransform(current, (number) => `${formatter.format(number)}${suffix}`);
  const fontSize = useTransform(current, (number) => {
    const length = formatter.format(number).replace(/\s/g, "").length;
    return length >= 9 ? "var(--energy-extra-compact)" : length >= 7 ? "var(--energy-compact)" : "var(--energy-size)";
  });
  return energy
    ? <motion.strong className="animated-number" style={{ fontSize }} title={`${formatter.format(value)} ккал`}>{text}</motion.strong>
    : <motion.span className="animated-number">{text}</motion.span>;
}
