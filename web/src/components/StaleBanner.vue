<script setup lang="ts">
defineProps<{
  generatedAt: Date;
}>();

function formatRelative(date: Date): string {
  const days = Math.floor((Date.now() - date.getTime()) / (24 * 60 * 60 * 1000));
  if (days <= 1) return "more than a day old";
  return `${days} days old`;
}
</script>

<template>
  <div class="stale" role="status">
    <strong>Data may be out of date</strong>
    <span>The latest published snapshot is {{ formatRelative(generatedAt) }}.</span>
  </div>
</template>

<style scoped>
.stale {
  background: rgba(233, 107, 39, 0.12);
  border-bottom: 1px solid rgba(233, 107, 39, 0.35);
  color: var(--color-ink);
  padding: var(--space-3) var(--space-5);
  display: flex;
  gap: var(--space-3);
  align-items: center;
  font-size: var(--fs-sm);
  flex-wrap: wrap;
}
</style>
