<script lang="ts">
  import type { FundSummary, PeerPosition } from "$lib/data/types";
  import { hasPeerGroup, MIN_PEERS, peerGapReason } from "$lib/fund";
  import { integer, percent2 } from "$lib/format";
  import PeerBand from "./PeerBand.svelte";

  const { peers, summary }: { peers: PeerPosition | null; summary: FundSummary } = $props();

  const group = $derived(hasPeerGroup(peers) ? peers : null);

  const METRICS = [
    {
      key: "fund_return",
      label: "Retorno 12m",
      reading: (share: string) => `${share} dos pares renderam menos`,
      betterNote: undefined,
    },
    {
      key: "volatility",
      label: "Volatilidade 12m",
      reading: (share: string) => `${share} dos pares oscilaram menos`,
      betterNote: "menor é melhor",
    },
    {
      key: "max_drawdown",
      label: "Drawdown máximo 12m",
      reading: (share: string) => `${share} dos pares caíram mais`,
      betterNote: "queda menor é melhor",
    },
  ];

  const rows = $derived(
    group === null
      ? []
      : METRICS.flatMap((entry) => {
          const metric = group.metrics[entry.key];
          return metric === undefined ? [] : [{ ...entry, metric }];
        }),
  );
</script>

<section class="card bg-base-100 border-base-content/10 border" aria-labelledby="peers-title">
  <div class="card-body gap-4 p-4 sm:p-5">
    {#if group === null}
      <h2 id="peers-title" class="text-base font-semibold">Posição entre pares</h2>
      <p class="text-base-content/70 text-sm">
        Sem grupo de pares: {peerGapReason(summary)}. Entram na comparação séries de Público Geral
        com 12 meses de histórico e pelo menos {MIN_PEERS} pares da mesma classificação ANBIMA.
      </p>
    {:else}
      <div class="flex flex-col gap-1">
        <h2 id="peers-title" class="text-base font-semibold">
          Entre {integer(group.peer_count)} pares de {group.anbima_classification} · {group.target_audience}
        </h2>
        <p class="text-base-content/70 text-xs">
          Janela de 12 meses. A barra marca a faixa central dos pares (P25 a P75) e o traço, a
          mediana; o ponto é o fundo. Percentil: fração dos pares com valor abaixo do fundo, empates
          contados pela metade.
        </p>
      </div>
      <div class="flex flex-col gap-5">
        {#each rows as row (row.key)}
          <PeerBand
            label={row.label}
            metric={row.metric}
            format={percent2}
            reading={row.reading}
            betterNote={row.betterNote}
          />
        {/each}
      </div>
    {/if}
  </div>
</section>
