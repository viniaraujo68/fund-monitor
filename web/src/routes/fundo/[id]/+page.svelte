<script lang="ts">
  import CumulativeReturnCard from "$lib/components/CumulativeReturnCard.svelte";
  import DrawdownCard from "$lib/components/DrawdownCard.svelte";
  import FundRegistry from "$lib/components/FundRegistry.svelte";
  import FundTiles from "$lib/components/FundTiles.svelte";
  import IssueList from "$lib/components/IssueList.svelte";
  import MonthlyFlowCard from "$lib/components/MonthlyFlowCard.svelte";
  import PageFrame from "$lib/components/PageFrame.svelte";
  import PeerPositionCard from "$lib/components/PeerPositionCard.svelte";
  import ReturnWindowsTable from "$lib/components/ReturnWindowsTable.svelte";
  import { date } from "$lib/format";

  const { data } = $props();

  const detail = $derived(data.detail);
  const summary = $derived(detail.summary);
</script>

{#snippet header()}
  {#if summary.subclass_name !== null || summary.structural_vehicle}
    <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
      {#if summary.subclass_name !== null}
        <p class="text-base-content/70 text-sm">Subclasse: {summary.subclass_name}</p>
      {/if}
      {#if summary.structural_vehicle}
        <span class="badge badge-outline badge-sm">veículo estrutural</span>
      {/if}
    </div>
  {/if}
{/snippet}

<PageFrame title={summary.display_name} description={summary.class_name} {header}>
  <FundRegistry {summary} windowStart={data.meta.window_start} />
  <FundTiles {detail} />
  <CumulativeReturnCard {detail} />
  <ReturnWindowsTable {detail} />
  <DrawdownCard {detail} />
  <MonthlyFlowCard {detail} />
  <PeerPositionCard peers={detail.peers} {summary} />
  <IssueList issues={detail.issues} />
  <p class="text-base-content/70 text-xs">
    Fonte: CVM (cadastro e informe diário), Bacen SGS, ANBIMA, B3. Dados até {date(data.meta.as_of)}.
  </p>
</PageFrame>
