<script setup lang="ts">
import { computed, useTemplateRef } from "vue";

import { COUNTY_DASH, DATA_PATHS, REPO_URL } from "@/constants";
import { useDataset } from "@/composables/useDataset";

const dialog = useTemplateRef<HTMLDialogElement>("dialog");
const { generatedAt } = useDataset();

// "Data as of" date, without the timezone abbreviation (we drop ", PDT").
const dataAsOfLabel = computed(() => {
  if (!generatedAt.value) return null;
  return generatedAt.value.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "America/Los_Angeles",
  });
});

function open() {
  dialog.value?.showModal();
}

function close() {
  dialog.value?.close();
}

function onBackdropClick(event: MouseEvent) {
  // Native <dialog> backdrop click target is the dialog itself; child clicks
  // bubble up. Only close when the user clicks outside the content.
  if (event.target === dialog.value) close();
}
</script>

<template>
  <button type="button" class="about-link" @click="open">About</button>
  <dialog ref="dialog" class="about-dialog" @click="onBackdropClick">
    <article class="about-dialog__inner" @click.stop>
      <header class="about-dialog__head">
        <h2>About</h2>
        <button type="button" class="about-dialog__close" aria-label="Close" @click="close">
          ×
        </button>
      </header>
      <div class="about-dialog__body">
        <p>
          A living analysis of how Altadena is rebuilding after the Eaton Fire of 2025. Altadata is
          free and open source. Built by Altadenans, for Altadena.
        </p>
        <p>
          <strong>Notice:</strong> This website actively being developed and may contain errors.
          Reference the
          <a :href="COUNTY_DASH" target="_blank" rel="noopener">County Dashboard</a> for official
          rebuild progress statistics.
        </p>
        <p>
          For questions, comments, or corrections please contact
          <a href="mailto:hello@altadata.org">hello@altadata.org</a>.
        </p>
        <p v-if="dataAsOfLabel" class="about-dialog__pill">Data as of {{ dataAsOfLabel }}</p>
        <nav class="about-dialog__links" aria-label="Resources">
          <RouterLink to="/quality-control" @click="close">Quality Control</RouterLink>
          <a :href="DATA_PATHS.parcelsCsv" download>Download parcels.csv</a>
          <a :href="REPO_URL" target="_blank" rel="noopener">Source Code</a>
        </nav>
      </div>
    </article>
  </dialog>
</template>

<style scoped>
.about-link {
  background: transparent;
  border: none;
  padding: 0;
  font-family: var(--font-display);
  font-size: var(--fs-md);
  letter-spacing: 0.01em;
  color: var(--color-ink);
  cursor: pointer;
}
.about-link:hover {
  color: var(--color-poppy);
}

.about-dialog {
  border: none;
  padding: 0;
  background: transparent;
  max-width: min(560px, 92vw);
  width: 100%;
  color: var(--color-ink);
}
.about-dialog::backdrop {
  background: rgba(42, 42, 42, 0.45);
}

.about-dialog__inner {
  background: var(--color-paper);
  border-radius: var(--radius-lg);
  padding: var(--space-5) var(--space-5) var(--space-6);
  box-shadow: var(--shadow-card);
}

.about-dialog__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
}
.about-dialog__head h2 {
  margin: 0;
  font-size: var(--fs-lg);
}

.about-dialog__close {
  background: transparent;
  border: none;
  font-size: 28px;
  line-height: 1;
  color: var(--color-ink-muted);
  padding: 0 var(--space-2);
}
.about-dialog__close:hover {
  color: var(--color-poppy);
}

.about-dialog__body {
  margin-top: var(--space-3);
  font-size: var(--fs-sm);
  color: var(--color-ink);
}
.about-dialog__body p {
  margin: 0 0 var(--space-4);
  color: var(--color-ink-muted);
}
.about-dialog__body strong {
  color: var(--color-ink);
}

.about-dialog__pill {
  display: inline-block;
  background: var(--color-paper-deep);
  border: 1px solid var(--color-rule);
  padding: var(--space-2) var(--space-3);
  border-radius: 999px;
  font-size: var(--fs-xs);
}

.about-dialog__links {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--fs-sm);
}
</style>
