const HTML_ENTITIES: Record<string, string> = {
  amp: "&",
  quot: '"',
  "#39": "'",
  lt: "<",
  gt: ">",
};

export function decodeHtml(value: string): string {
  return value.replace(/&(amp|quot|#39|lt|gt);/g, (entity, name) => (
    HTML_ENTITIES[name] ?? entity
  ));
}
