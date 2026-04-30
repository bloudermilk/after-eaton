<script setup lang="ts">
import { computed } from "vue";
import MarkdownIt from "markdown-it";
import anchor from "markdown-it-anchor";

import md from "@/assets/methodology.md?raw";

const renderer = new MarkdownIt({ html: false, linkify: true, typographer: true });
renderer.use(anchor, {
  permalink: anchor.permalink.linkInsideHeader({
    symbol: "#",
    placement: "before",
    ariaHidden: true,
  }),
});

interface TocEntry {
  level: number;
  text: string;
  slug: string;
}

const html = computed(() => renderer.render(md));

// Extract level-2 and level-3 headings from the source for the TOC.
const toc = computed<TocEntry[]>(() => {
  const lines = md.split("\n");
  const out: TocEntry[] = [];
  for (const line of lines) {
    const m = /^(#{2,3})\s+(.+?)\s*$/.exec(line);
    if (!m) continue;
    const level = m[1]!.length;
    const text = m[2]!;
    const slug = text
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .trim()
      .replace(/\s+/g, "-");
    out.push({ level, text, slug });
  }
  return out;
});

// Hash-based routing means the URL hash holds the route (e.g. `#/methodology`),
// so we can't rely on `<a href="#slug">` for in-page anchors — that would clobber
// the route. Intercept clicks and scroll the heading into view manually.
function scrollToSlug(slug: string): void {
  const el = document.getElementById(slug);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function onTocClick(event: MouseEvent, slug: string): void {
  event.preventDefault();
  scrollToSlug(slug);
}

function onArticleClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null;
  const anchorEl = target?.closest("a.header-anchor") as HTMLAnchorElement | null;
  if (!anchorEl) return;
  const href = anchorEl.getAttribute("href");
  if (!href || !href.startsWith("#")) return;
  event.preventDefault();
  scrollToSlug(href.slice(1));
}
</script>

<template>
  <main class="methodology">
    <aside class="methodology__toc" aria-label="Table of contents">
      <h2>Contents</h2>
      <ul>
        <li v-for="entry in toc" :key="entry.slug" :class="`toc-l${entry.level}`">
          <a :href="`#${entry.slug}`" @click="onTocClick($event, entry.slug)">{{ entry.text }}</a>
        </li>
      </ul>
    </aside>
    <!-- eslint-disable-next-line vue/no-v-html -- bundled markdown from our own repo, not user input -->
    <article class="methodology__article" @click="onArticleClick" v-html="html" />
  </main>
</template>

<style scoped>
.methodology {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-6);
}

@media (min-width: 1000px) {
  .methodology {
    grid-template-columns: 220px minmax(0, 1fr);
  }
}

.methodology__toc {
  font-size: var(--fs-sm);
}
@media (min-width: 1000px) {
  .methodology__toc {
    position: sticky;
    top: var(--space-5);
    align-self: start;
    max-height: calc(100vh - var(--space-6));
    overflow-y: auto;
    padding-right: var(--space-3);
    border-right: 1px solid var(--color-rule);
  }
}

.methodology__toc h2 {
  font-size: var(--fs-sm);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-ink-muted);
  font-family: var(--font-sans);
  font-weight: 600;
  margin: 0 0 var(--space-2);
}

.methodology__toc ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.methodology__toc .toc-l3 {
  margin-left: var(--space-3);
}

.methodology__toc a {
  color: var(--color-ink-muted);
  text-decoration: none;
}
.methodology__toc a:hover {
  color: var(--color-poppy);
  text-decoration: underline;
}

.methodology__article {
  max-width: 720px;
}

.methodology__article :deep(h1) {
  font-size: var(--fs-2xl);
  margin-top: 0;
}
.methodology__article :deep(h2) {
  margin-top: var(--space-7);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-rule);
}
.methodology__article :deep(h3) {
  margin-top: var(--space-5);
}

.methodology__article :deep(p),
.methodology__article :deep(li) {
  font-size: var(--fs-md);
  line-height: 1.7;
}

.methodology__article :deep(table) {
  margin: var(--space-4) 0;
  font-size: var(--fs-sm);
}

.methodology__article :deep(blockquote) {
  border-left: 3px solid var(--color-alluvial);
  margin: var(--space-4) 0;
  padding: var(--space-2) var(--space-4);
  color: var(--color-ink-muted);
}

.methodology__article :deep(code) {
  background: var(--color-paper-deep);
  padding: 1px 5px;
  border-radius: var(--radius-sm);
}
.methodology__article :deep(pre code) {
  background: transparent;
  padding: 0;
}

.methodology__article :deep(.header-anchor) {
  color: var(--color-rule);
  text-decoration: none;
  margin-right: var(--space-2);
}
.methodology__article :deep(h2:hover .header-anchor),
.methodology__article :deep(h3:hover .header-anchor) {
  color: var(--color-poppy);
}
</style>
