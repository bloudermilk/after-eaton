<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string;
    subtitle?: string;
    // When interactive, the header is a button that toggles the metric on the
    // map; `active` reflects the current selection.
    interactive?: boolean;
    active?: boolean;
  }>(),
  { subtitle: undefined, interactive: false, active: false },
);

const emit = defineEmits<{ toggle: [] }>();
</script>

<template>
  <section
    class="stat-card"
    :class="{ 'stat-card--active': active }"
    :aria-labelledby="`stat-${title.replace(/\s+/g, '-')}`"
  >
    <header class="stat-card__head">
      <component
        :is="interactive ? 'button' : 'div'"
        :type="interactive ? 'button' : undefined"
        class="stat-card__heading"
        :class="{ 'stat-card__heading--button': interactive }"
        :aria-pressed="interactive ? active : undefined"
        @click="interactive && emit('toggle')"
      >
        <h2 :id="`stat-${title.replace(/\\s+/g, '-')}`" class="stat-card__title">
          {{ title }}
        </h2>
        <p v-if="subtitle" class="stat-card__subtitle">{{ subtitle }}</p>
      </component>
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
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.stat-card--active {
  border-color: var(--color-poppy);
  box-shadow:
    0 0 0 1px var(--color-poppy),
    var(--shadow-card);
}

.stat-card__heading {
  text-align: left;
}

.stat-card__heading--button {
  appearance: none;
  border: 0;
  background: transparent;
  padding: var(--space-1) var(--space-2);
  margin: calc(-1 * var(--space-1)) calc(-1 * var(--space-2));
  border-radius: var(--radius-md);
  font: inherit;
  color: inherit;
  cursor: pointer;
  display: block;
  width: 100%;
  transition: background 0.15s ease;
}

.stat-card__heading--button:hover {
  background: var(--color-paper-deep);
}

.stat-card__heading--button:focus-visible {
  outline: 2px solid var(--color-poppy);
  outline-offset: 2px;
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
