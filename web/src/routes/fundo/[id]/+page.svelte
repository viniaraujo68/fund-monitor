<script lang="ts">
  import PageFrame from "$lib/components/PageFrame.svelte";

  const { data } = $props();
</script>

<PageFrame title={data.detail.summary.display_name}>
  <p class="text-base-content/70 text-sm">Página em construção.</p>
</PageFrame>
