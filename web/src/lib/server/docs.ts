const decisionFiles = import.meta.glob<string>("$docs/DECISIONS.md", {
  eager: true,
  query: "?raw",
  import: "default",
});

export const decisions: string | null = Object.values(decisionFiles)[0] ?? null;
