<script lang="ts">
  import { Copyable } from "@viniaraujo68/plinth/components";
  import type { FundSummary, IsoDate } from "$lib/data/types";
  import { cnpj, DASH, date } from "$lib/format";
  import { benchmarkList } from "$lib/labels";

  const { summary, windowStart }: { summary: FundSummary; windowStart: IsoDate } = $props();

  const facts = $derived<{ term: string; value: string }[]>([
    { term: "Classificação CVM", value: summary.cvm_classification ?? DASH },
    { term: "Classificação ANBIMA", value: summary.anbima_classification ?? DASH },
    { term: "Público-alvo", value: summary.target_audience ?? DASH },
    { term: "Condomínio", value: summary.condominium ?? DASH },
    { term: "Indicador de desempenho declarado", value: summary.performance_benchmark ?? DASH },
    { term: "Comparado com", value: benchmarkList(summary.benchmarks) },
    { term: `Primeira cota na janela (desde ${date(windowStart)})`, value: date(summary.first_date) },
    { term: "Última cota", value: date(summary.last_date) },
  ]);
</script>

<section class="card bg-base-100 border-base-content/10 border" aria-labelledby="registry-title">
  <div class="card-body gap-3 p-4 sm:p-5">
    <h2 id="registry-title" class="text-base font-semibold">Cadastro</h2>
    <dl class="grid grid-cols-2 gap-x-6 gap-y-3 lg:grid-cols-3">
      <div class="col-span-2 flex min-w-0 flex-col gap-0.5 sm:col-span-1">
        <dt class="text-base-content/70 text-xs">CNPJ da classe</dt>
        <dd class="text-sm tabular-nums">
          <Copyable
            copyableText={summary.cnpj}
            copyLabel="Copiar CNPJ sem máscara"
            copiedLabel="CNPJ copiado"
          >
            {cnpj(summary.cnpj)}
          </Copyable>
        </dd>
      </div>
      {#if summary.subclass_id !== null}
        <div class="col-span-2 flex min-w-0 flex-col gap-0.5 sm:col-span-1">
          <dt class="text-base-content/70 text-xs">ID da subclasse</dt>
          <dd class="font-mono text-sm">
            <Copyable
              copyableText={summary.subclass_id}
              copyLabel="Copiar ID da subclasse"
              copiedLabel="ID da subclasse copiado"
            >
              {summary.subclass_id}
            </Copyable>
          </dd>
        </div>
      {/if}
      {#each facts as fact (fact.term)}
        <div class="flex min-w-0 flex-col gap-0.5">
          <dt class="text-base-content/70 text-xs">{fact.term}</dt>
          <dd class="text-sm tabular-nums">{fact.value}</dd>
        </div>
      {/each}
    </dl>
    {#if summary.inherited_until !== null}
      <p class="text-base-content/70 text-xs" role="note">
        Cota até {date(summary.inherited_until)} herdada da classe (a subclasse nasceu com a mesma cota).
      </p>
    {/if}
  </div>
</section>
