<script lang="ts">
  const { text, height = "h-72" }: { text: string; height?: string } = $props();
</script>

<div
  class={[
    "border-base-content/15 text-base-content/70 flex w-full items-center justify-center rounded-box border border-dashed p-6 text-center text-sm",
    height,
  ]}
  role="note"
>
  {text}
</div>
