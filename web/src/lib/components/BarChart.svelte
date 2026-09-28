<script lang="ts">
  import { Chart, type ChartConfiguration } from "chart.js";
  import { getThemeContext } from "@viniaraujo68/plinth/theme";
  import { registerCharts } from "$lib/charts/register";
  import { readChartColors, slotColor } from "$lib/charts/theme";
  import { DASH } from "$lib/format";
  import ChartNotice from "./ChartNotice.svelte";

  export interface BarSeries {
    label: string;
    data: (number | null)[];
    slot: number;
    colors?: number[];
  }

  const {
    labels,
    series,
    formatValue,
    formatAxis,
    ariaLabel,
    insufficientText = "Ainda não há períodos suficientes para desenhar as barras.",
  }: {
    labels: string[];
    series: BarSeries[];
    formatValue: (value: number) => string;
    formatAxis: (value: number) => string;
    ariaLabel: string;
    insufficientText?: string;
  } = $props();

  const theme = getThemeContext();
  let canvas = $state<HTMLCanvasElement>();
  let host = $state<HTMLDivElement>();

  const drawable = $derived(labels.length >= 2 && series.length > 0);

  $effect(() => {
    const element = canvas;
    const container = host;
    const rows = labels;
    const bars = series;
    void theme.dark;

    if (!element || !container) return;

    registerCharts();
    const colors = readChartColors(container);

    const config: ChartConfiguration<"bar"> = {
      type: "bar",
      data: {
        labels: rows,
        datasets: bars.map((entry) => ({
          label: entry.label,
          data: entry.data,
          backgroundColor:
            entry.colors === undefined
              ? slotColor(colors, entry.slot)
              : entry.colors.map((slot) => slotColor(colors, slot)),
          borderRadius: 3,
          maxBarThickness: 24,
          barPercentage: 0.9,
          categoryPercentage: 0.75,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },
        layout: { padding: { top: 6, right: 6 } },
        plugins: {
          legend: {
            display: bars.length > 1,
            position: "bottom",
            labels: {
              color: colors.ink,
              usePointStyle: true,
              pointStyle: "rect",
              boxWidth: 8,
              boxHeight: 8,
              padding: 16,
            },
          },
          tooltip: {
            backgroundColor: colors.surface,
            titleColor: colors.ink,
            bodyColor: colors.ink,
            borderColor: colors.grid,
            borderWidth: 1,
            padding: 10,
            usePointStyle: true,
            callbacks: {
              label: (item) =>
                item.parsed.y === null
                  ? ` ${item.dataset.label ?? ""}: ${DASH}`
                  : ` ${item.dataset.label ?? ""}: ${formatValue(item.parsed.y)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { color: colors.grid },
            ticks: { color: colors.muted, maxRotation: 0, autoSkip: true, autoSkipPadding: 8 },
          },
          y: {
            beginAtZero: true,
            grid: {
              color: (context) => (context.tick.value === 0 ? colors.muted : colors.grid),
            },
            border: { display: false },
            ticks: {
              color: colors.muted,
              maxTicksLimit: 6,
              callback: (value) => formatAxis(Number(value)),
            },
          },
        },
      },
    };

    const chart = new Chart(element, config);
    return () => chart.destroy();
  });
</script>

{#if drawable}
  <div bind:this={host} class="relative h-72 w-full" role="img" aria-label={ariaLabel}>
    <canvas bind:this={canvas}></canvas>
  </div>
{:else}
  <ChartNotice text={insufficientText} />
{/if}
