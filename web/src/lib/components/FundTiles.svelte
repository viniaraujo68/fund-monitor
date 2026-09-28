<script lang="ts">
  import type { FundDetail, RiskRow } from "$lib/data/types";
  import { findRisk, findWindow, hasHistory } from "$lib/fund";
  import { date, integer, money, moneyCompact, peerRank, percent2, ratio2 } from "$lib/format";
  import { benchmarkLabel } from "$lib/labels";
  import StatTile from "./StatTile.svelte";

  const { detail }: { detail: FundDetail } = $props();

  const NO_HISTORY = "menos de 12 meses de série";

  const summary = $derived(detail.summary);
  const risk = $derived(findRisk(detail, "12m"));
  const covered = $derived(hasHistory(findWindow(detail, "12m")));
  const missing = (value: number | null, reason: string): string | undefined =>
    value === null ? (covered ? reason : NO_HISTORY) : undefined;

  const netAssetsHint = $derived(
    [
      summary.last_date === null ? null : `em ${date(summary.last_date)}`,
      summary.shareholders === null
        ? null
        : `${integer(summary.shareholders)} ${summary.shareholders === 1 ? "cotista" : "cotistas"}`,
    ]
      .filter((part) => part !== null)
      .join(" · "),
  );

  const returnHint = $derived(
    summary.pct_cdi_12m === null
      ? missing(summary.return_12m, "sem retorno na janela")
      : `${percent2(summary.pct_cdi_12m)} do CDI`,
  );

  const drawdownHint = (row: RiskRow | undefined): string | undefined => {
    if (row === undefined || row.max_drawdown === null) return NO_HISTORY;
    if (row.peak_date === null || row.trough_date === null) return "sem queda na janela";
    const recovery =
      row.recovery_date === null ? "sem recuperação" : `recuperado em ${date(row.recovery_date)}`;
    return `de ${date(row.peak_date)} a ${date(row.trough_date)} · ${recovery}`;
  };

  const market = $derived(
    summary.market_benchmark === null ? null : benchmarkLabel(summary.market_benchmark),
  );
</script>

<section class="flex flex-col gap-2" aria-labelledby="fund-tiles-title">
  <h2 id="fund-tiles-title" class="sr-only">Indicadores</h2>
  <div class="grid grid-cols-2 gap-3 md:grid-cols-3">
    <StatTile
      label="Patrimônio líquido"
      value={moneyCompact(summary.net_assets)}
      detail={money(summary.net_assets)}
      hint={netAssetsHint}
    />
    <StatTile
      label="Captação líquida 12m"
      value={moneyCompact(summary.net_flow_12m)}
      detail={money(summary.net_flow_12m)}
      hint={summary.flow_window_partial === true ? "janela parcial" : undefined}
    />
    <StatTile label="Retorno 12m" value={percent2(summary.return_12m)} hint={returnHint} />
    <StatTile
      label="Volatilidade 12m"
      value={percent2(summary.volatility_12m)}
      hint={missing(summary.volatility_12m, "menos de 60 observações") ?? "anualizada"}
    />
    <StatTile
      label="Sharpe 12m"
      value={ratio2(summary.sharpe_12m)}
      hint={missing(summary.sharpe_12m, "menos de 60 observações") ??
        "CDI como taxa livre de risco"}
    />
    <StatTile
      label="Drawdown máximo 12m"
      value={percent2(summary.max_drawdown_12m)}
      hint={drawdownHint(risk)}
    />
    {#if market !== null}
      <StatTile
        label="Beta 12m"
        value={ratio2(risk?.beta)}
        hint={missing(risk?.beta ?? null, "menos de 60 observações") ?? `contra ${market}`}
      />
      <StatTile
        label="Tracking error 12m"
        value={percent2(risk?.tracking_error)}
        hint={missing(risk?.tracking_error ?? null, "menos de 60 observações") ??
          `contra ${market}`}
      />
    {/if}
    <StatTile
      label="Posição entre pares"
      value={peerRank(detail.peers?.metrics.fund_return?.percentile, detail.peers?.peer_count ?? 0)}
      hint={detail.peers === null ? "sem grupo de pares" : "percentil do retorno 12m"}
    />
  </div>
</section>
