<script lang="ts">
  import { severityBadgeClass, severityLabel } from "$lib/labels";

  const { severity }: { severity: string } = $props();
</script>

<span class={["badge badge-sm shrink-0", severityBadgeClass(severity)]}>
  {severityLabel(severity)}
</span>
