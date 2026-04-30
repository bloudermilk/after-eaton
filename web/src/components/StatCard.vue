<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
}>();
</script>

<template>
  <section class="stat-card" :aria-labelledby="`stat-${title.replace(/\s+/g, '-')}`">
    <header class="stat-card__head">
      <div>
        <h2 :id="`stat-${title.replace(/\\s+/g, '-')}`" class="stat-card__title">
          {{ title }}
        </h2>
        <p v-if="subtitle" class="stat-card__subtitle">{{ subtitle }}</p>
      </div>
      <slot name="info" />
    </header>
    <div class="stat-card__visual">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.stat-card {
  background: var(--color-paper);
  border: 1px solid var(--color-rule);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  box-shadow: var(--shadow-card);
}

@media (max-width: 480px) {
  .stat-card {
    padding: var(--space-4);
  }
}

.stat-card__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
}

.stat-card__title {
  font-size: var(--fs-md);
  font-family: var(--font-display);
  margin: 0;
}

.stat-card__subtitle {
  margin: var(--space-1) 0 0;
  color: var(--color-ink-muted);
  font-size: var(--fs-sm);
}

.stat-card__visual {
  flex: 1;
  display: flex;
  align-items: stretch;
  justify-content: center;
}
</style>
