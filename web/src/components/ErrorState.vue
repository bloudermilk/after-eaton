<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  error: Error;
}>();

const isDev = import.meta.env.DEV;

const message = computed(() => props.error.message);
</script>

<template>
  <div class="error" role="alert">
    <h2>We couldn't load the data</h2>
    <p>The site bundles its data at deploy time, so this is unusual. Try reloading.</p>
    <p class="error__detail">
      <code>{{ message }}</code>
    </p>
    <p v-if="isDev" class="error__hint">
      Running locally? Make sure <code>web/public/data/</code> contains
      <code>summary.json</code> and <code>qc-report.json</code> — run
      <code>npm run data:fetch-local</code> or <code>npm run data:fetch-release</code>.
    </p>
  </div>
</template>

<style scoped>
.error {
  background: var(--color-paper-deep);
  border-left: 4px solid var(--color-danger);
  padding: var(--space-5);
  border-radius: var(--radius-md);
  margin: var(--space-5) 0;
}

.error__detail code {
  background: rgba(179, 73, 49, 0.08);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  color: var(--color-danger);
}

.error__hint {
  color: var(--color-ink-muted);
  font-size: var(--fs-sm);
}
</style>
