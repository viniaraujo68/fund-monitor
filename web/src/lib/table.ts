interface LabeledColumn {
  label: string;
}

export const TABLE_LABELS = {
  locale: "pt-BR",
  sortLabel: (column: LabeledColumn): string => `Ordenar por ${column.label}`,
  columnsLabel: "Colunas",
  resetColumnsLabel: "Restaurar colunas",
  moveColumnLabel: (column: LabeledColumn, direction: "up" | "down"): string =>
    `Mover ${column.label} para ${direction === "up" ? "cima" : "baixo"}`,
};
