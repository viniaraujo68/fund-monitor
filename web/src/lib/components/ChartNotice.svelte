<script lang="ts">
  const { text }: { text: string } = $props();
</script>

<div
  class="border-base-content/15 text-base-content/70 rounded-box flex h-72 w-full items-center justify-center border border-dashed p-6 text-center text-sm"
  role="note"
>
  {text}
</div>
