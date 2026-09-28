export const icons: Record<string, string[]> = {
  overview: ["M3 3h7v9H3Z", "M14 3h7v5h-7Z", "M14 12h7v9h-7Z", "M3 16h7v5H3Z"],
};

export const iconPaths = (name: string | undefined): string[] =>
  name === undefined ? [] : (icons[name] ?? []);
