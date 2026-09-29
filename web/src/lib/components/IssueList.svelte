<script lang="ts">
  import type { Issue, IssueCounts } from "$lib/data/types";
  import { date, integer } from "$lib/format";
  import { byTriage, issueMeasureText, issueText, ruleLabel, triageDetail } from "$lib/issues";
  import { OPEN_SEVERITIES, untreatedInfo } from "$lib/labels";
  import SeverityBadge from "./SeverityBadge.svelte";
  import StatusBadge from "./StatusBadge.svelte";

  const { issues, openIssues }: { issues: Issue[]; openIssues: IssueCounts } = $props();

  const ordered = $derived([...issues].sort(byTriage));

  const openCount = $derived(OPEN_SEVERITIES.reduce((sum, level) => sum + openIssues[level], 0));
</script>

<section class="card bg-base-100 border-base-content/10 border" aria-labelledby="issues-title">
  <div class="card-body gap-3 p-4 sm:p-5">
    <h2 id="issues-title" class="text-base font-semibold">
      Alertas de qualidade
      {#if issues.length > 0}
        <span class="text-base-content/70 font-normal tabular-nums">
          · {integer(openCount)}
          {openCount === 1 ? "aberto" : "abertos"} de {integer(issues.length)}
        </span>
      {/if}
    </h2>
    {#if issues.length === 0}
      <p class="text-base-content/70 text-sm">Nenhum alerta de qualidade nesta série.</p>
    {:else}
      <ul class="divide-base-content/10 flex flex-col divide-y">
        {#each ordered as issue, index (index)}
          {@const triage = triageDetail(issue.note, issue.treated_on)}
          {@const measure = issueMeasureText(issue)}
          <li class="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0">
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
              {#if !untreatedInfo(issue.status, issue.severity)}
                <StatusBadge status={issue.status} />
              {/if}
              <SeverityBadge severity={issue.severity} />
              <span class="text-sm font-medium">{ruleLabel(issue.rule)}</span>
              {#if issue.date !== null}
                <span class="text-base-content/70 text-xs tabular-nums">{date(issue.date)}</span>
              {/if}
            </div>
            <p class="text-sm">{issueText(issue)}</p>
            {#if measure !== null}
              <p class="text-base-content/70 text-xs tabular-nums">{measure}</p>
            {/if}
            {#if triage !== ""}
              <p class="text-base-content/70 text-xs">{triage}</p>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</section>
