import { Marked } from "marked";

export interface Heading {
  id: string;
  text: string;
}

export interface RenderedMarkdown {
  html: string;
  headings: Heading[];
}

const INDEX_DEPTH = 2;

const slugify = (text: string): string =>
  text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

const escapeAttribute = (text: string): string => text.replace(/&/g, "&amp;").replace(/"/g, "&quot;");

export const renderMarkdown = (source: string): RenderedMarkdown => {
  const headings: Heading[] = [];
  const seen = new Map<string, number>();

  const uniqueId = (text: string): string => {
    const base = slugify(text) || "secao";
    const count = (seen.get(base) ?? 0) + 1;
    seen.set(base, count);
    return count === 1 ? base : `${base}-${count}`;
  };

  const marked = new Marked({
    gfm: true,
    async: false,
    renderer: {
      heading({ tokens, depth }) {
        if (depth === 1) return "";
        const text = this.parser.parseInline(tokens, this.parser.textRenderer);
        const id = uniqueId(text);
        if (depth === INDEX_DEPTH) headings.push({ id, text });
        return `<h${depth} id="${escapeAttribute(id)}">${this.parser.parseInline(tokens)}</h${depth}>\n`;
      },
    },
  });

  const html = marked
    .parse(source, { async: false })
    .replaceAll("<table>", '<div class="overflow-x-auto"><table class="table table-sm table-zebra">')
    .replaceAll("</table>", "</table></div>");

  return { html, headings };
};
