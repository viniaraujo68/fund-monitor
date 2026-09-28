import { createCssColorReader } from "@viniaraujo68/plinth/theme";

export const SERIES_TOKENS = [
  "--color-success",
  "--color-primary",
  "--color-warning",
  "--color-info",
  "--color-error",
] as const;

const POINT_STYLES = ["circle", "rect", "triangle", "rectRot", "star"] as const;

export const SERIES_SLOTS = SERIES_TOKENS.length;

export interface ChartColors {
  series: string[];
  seriesSoft: string[];
  ink: string;
  muted: string;
  grid: string;
  surface: string;
}

const FALLBACK: ChartColors = {
  series: ["#1c8a4c", "#5d3ac4", "#a67a0f", "#2876c7", "#b64337"],
  seriesSoft: [
    "rgba(28, 138, 76, 0.18)",
    "rgba(93, 58, 196, 0.18)",
    "rgba(166, 122, 15, 0.18)",
    "rgba(40, 118, 199, 0.18)",
    "rgba(182, 67, 55, 0.18)",
  ],
  ink: "rgb(27, 29, 34)",
  muted: "rgba(27, 29, 34, 0.7)",
  grid: "rgba(27, 29, 34, 0.12)",
  surface: "rgb(255, 255, 255)",
};

const tokenAt = (slot: number): (typeof SERIES_TOKENS)[number] =>
  SERIES_TOKENS[slot % SERIES_SLOTS] ?? SERIES_TOKENS[0];

export const slotVar = (slot: number): string => `var(${tokenAt(slot)})`;

export const readChartColors = (host: HTMLElement): ChartColors => {
  const reader = createCssColorReader(host);
  try {
    return {
      series: SERIES_TOKENS.map((token, slot) =>
        reader.read(`var(${token})`, FALLBACK.series[slot] ?? FALLBACK.ink),
      ),
      seriesSoft: SERIES_TOKENS.map((token, slot) =>
        reader.read(
          `color-mix(in srgb, var(${token}) 18%, transparent)`,
          FALLBACK.seriesSoft[slot] ?? FALLBACK.grid,
        ),
      ),
      ink: reader.read("var(--color-base-content)", FALLBACK.ink),
      muted: reader.read(
        "color-mix(in srgb, var(--color-base-content) 70%, transparent)",
        FALLBACK.muted,
      ),
      grid: reader.read(
        "color-mix(in srgb, var(--color-base-content) 12%, transparent)",
        FALLBACK.grid,
      ),
      surface: reader.read("var(--color-base-100)", FALLBACK.surface),
    };
  } finally {
    reader.dispose();
  }
};

export const slotColor = (colors: ChartColors, slot: number): string =>
  colors.series[slot % SERIES_SLOTS] ?? FALLBACK.series[0] ?? FALLBACK.ink;

export const slotSoftColor = (colors: ChartColors, slot: number): string =>
  colors.seriesSoft[slot % SERIES_SLOTS] ?? FALLBACK.grid;

export const slotPointStyle = (slot: number): (typeof POINT_STYLES)[number] =>
  POINT_STYLES[slot % POINT_STYLES.length] ?? "circle";
