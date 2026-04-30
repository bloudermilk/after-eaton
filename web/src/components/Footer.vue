<script setup lang="ts">
import { computed } from "vue";

import { DATA_PATHS, REPO_URL } from "@/constants";
import { useDataset } from "@/composables/useDataset";

const { generatedAt } = useDataset();

const dataAsOfLabel = computed(() => {
  if (!generatedAt.value) return null;
  return generatedAt.value.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "America/Los_Angeles",
    timeZoneName: "short",
  });
});
</script>

<template>
  <footer class="site-footer">
    <div class="site-footer__inner">
      <div class="site-footer__about">
        <p>
          <strong>After Eaton</strong> is free and open source. Built by Altadenans, for Altadena.
          <a :href="REPO_URL" target="_blank" rel="noopener">View source on GitHub</a>.
        </p>
        <p v-if="dataAsOfLabel" class="site-footer__pill">Data as of {{ dataAsOfLabel }}</p>
      </div>
      <nav class="site-footer__links" aria-label="Footer">
        <RouterLink to="/methodology">Methodology</RouterLink>
        <RouterLink to="/quality-control">Quality Control</RouterLink>
        <a :href="DATA_PATHS.parcelsCsv" download>Download parcels.csv</a>
      </nav>
      <p class="site-footer__license">MIT License.</p>
    </div>
  </footer>
</template>

<style scoped>
.site-footer {
  border-top: 1px solid var(--color-rule);
  background: var(--color-paper-deep);
  margin-top: var(--space-8);
}

.site-footer__inner {
  max-width: var(--container-max);
  margin: 0 auto;
  padding: var(--space-6) var(--space-5);
  display: grid;
  gap: var(--space-5);
  grid-template-columns: 1.6fr 1fr;
  align-items: start;
}

.site-footer__about p {
  margin: 0 0 var(--space-3);
  color: var(--color-ink-muted);
  font-size: var(--fs-sm);
}
.site-footer__about strong {
  color: var(--color-ink);
}

.site-footer__pill {
  display: inline-block;
  background: var(--color-paper);
  border: 1px solid var(--color-rule);
  padding: var(--space-2) var(--space-3);
  border-radius: 999px;
  font-size: var(--fs-xs);
}

.site-footer__links {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--fs-sm);
}

.site-footer__license {
  grid-column: 1 / -1;
  color: var(--color-ink-muted);
  font-size: var(--fs-xs);
  margin: 0;
  border-top: 1px solid var(--color-rule);
  padding-top: var(--space-4);
}

@media (max-width: 720px) {
  .site-footer__inner {
    grid-template-columns: 1fr;
    padding: var(--space-5) var(--space-4);
  }
}
</style>
