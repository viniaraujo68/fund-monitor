<script lang="ts">
  import { Chart, type ChartConfiguration } from "chart.js";
  import { getThemeContext } from "@viniaraujo68/plinth/theme";
  import { registerCharts } from "$lib/charts/register";
  import { readChartColors, slotColor, slotPointStyle, slotSoftColor } from "$lib/charts/theme";
  import ChartNotice from "./ChartNotice.svelte";

  export interface LineSeries {
    label: string;
    data: (number | null)[];
    slot: number;
    dashed?: boolean;
  }

  const {
    labels,
    series,
    formatValue,
    formatAxis,
    ariaLabel,
    axisTitle,
    height = "h-72",
    points = true,
    fill = false,
    max,
    insufficientText = "Ainda não há pontos suficientes para desenhar a linha.",
  }: {
    labels: string[];
    series: LineSeries[];
    formatValue: (value: number) => string;
    formatAxis: (value: number) => string;
    ariaLabel: string;
    axisTitle?: string;
    height?: string;
    points?: boolean;
    fill?: boolean;
    max?: number;
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
    const lines = series;
    const withPoints = points;
    const withFill = fill;
    const ceiling = max;
    void theme.dark;

    if (element === undefined || container === undefined) return;

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
          borderDash: entry.dashed === true ? [6, 4] : [],
          tension: 0,
          spanGaps: true,
          pointStyle: slotPointStyle(entry.slot),
          pointRadius: withPoints ? 4 : 0,
          pointHoverRadius: withPoints ? 6 : 4,
          pointBorderColor: colors.surface,
          pointBorderWidth: withPoints ? 2 : 1,
          pointHoverBackgroundColor: slotColor(colors, entry.slot),
          pointHitRadius: withPoints ? 12 : 6,
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
            mode: "index",
            intersect: false,
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
                  ? ` ${item.dataset.label ?? ""}: —`
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
              maxTicksLimit: withPoints ? undefined : 8,
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
  <div bind:this={host} class={["relative w-full", height]} role="img" aria-label={ariaLabel}>
    <canvas bind:this={canvas}></canvas>
  </div>
{:else}
  <ChartNotice text={insufficientText} {height} />
{/if}
