<script lang="ts">
  import { Chart, type ChartConfiguration } from "chart.js";
  import { getThemeContext } from "@viniaraujo68/plinth/theme";
  import { registerCharts } from "$lib/charts/register";
  import { readChartColors, slotColor, slotPointStyle, slotSoftColor } from "$lib/charts/theme";
  import { DASH } from "$lib/format";
  import ChartNotice from "./ChartNotice.svelte";

  export interface LineSeries {
    label: string;
    data: (number | null)[];
    slot: number;
  }

  const {
    labels,
    series,
    formatValue,
    formatAxis,
    ariaLabel,
    axisTitle,
    fill = false,
    max,
    insufficientText = "Ainda não há pontos suficientes para desenhar a linha.",
  }: {
    labels: string[];
    series: LineSeries[];
    formatValue: (value: number) => string;
    formatAxis: (value: number, step: number) => string;
    ariaLabel: string;
    axisTitle?: string;
    fill?: boolean;
    max?: number;
    insufficientText?: string;
  } = $props();

  const theme = getThemeContext();
  let canvas = $state<HTMLCanvasElement>();
  let host = $state<HTMLDivElement>();

  const tickStep = (ticks: { value: number }[]): number =>
    ticks.slice(1).reduce((step, tick, index) => {
      const gap = Math.abs(tick.value - (ticks[index]?.value ?? tick.value));
      return gap > 0 && (step === 0 || gap < step) ? gap : step;
    }, 0);

  const drawable = $derived(labels.length >= 2 && series.length > 0);

  $effect(() => {
    const element = canvas;
    const container = host;
    const rows = labels;
    const lines = series;
    const withFill = fill;
    const ceiling = max;
    void theme.dark;

    if (!element || !container) return;

    registerCharts();
    const colors = readChartColors(container);

    const config: ChartConfiguration<"line"> = {
      type: "line",
      data: {
        labels: rows,
        datasets: lines.map((entry) => ({
          label: entry.label,
          data: entry.data,
          borderColor: slotColor(colors, entry.slot),
          backgroundColor: withFill
            ? slotSoftColor(colors, entry.slot)
            : slotColor(colors, entry.slot),
          fill: withFill ? "origin" : false,
          borderWidth: 2,
          tension: 0,
          spanGaps: true,
          pointStyle: slotPointStyle(entry.slot),
          pointRadius: 0,
          pointHoverRadius: 4,
          pointBorderColor: colors.surface,
          pointBorderWidth: 1,
          pointHoverBackgroundColor: slotColor(colors, entry.slot),
          pointHitRadius: 6,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },
        layout: { padding: { left: 6, right: 10, top: 6 } },
        plugins: {
          legend: {
            display: lines.length > 1,
            position: "bottom",
            labels: {
              color: colors.ink,
              usePointStyle: true,
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
            ticks: {
              color: colors.muted,
              maxRotation: 0,
              autoSkip: true,
              autoSkipPadding: 16,
              maxTicksLimit: 8,
            },
          },
          y: {
            max: ceiling,
            grid: { color: colors.grid },
            border: { display: false },
            title:
              axisTitle === undefined
                ? undefined
                : { display: true, text: axisTitle, color: colors.muted },
            ticks: {
              color: colors.muted,
              maxTicksLimit: 5,
              callback: (value, _index, ticks) => formatAxis(Number(value), tickStep(ticks)),
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
