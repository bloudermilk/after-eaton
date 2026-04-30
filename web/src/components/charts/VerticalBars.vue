<script setup lang="ts">
import { computed } from "vue";

interface Bucket {
  label: string;
  value: number;
  color?: string;
}

const props = defineProps<{
  buckets: Bucket[];
  // Universe size (e.g. all parcels actually rebuilding) — used as
  // denominator when rendering each bar's percent label.
  denominator?: number;
}>();

const max = computed(() => Math.max(1, ...props.buckets.map((b) => b.value)));

function pctLabel(value: number): string {
  if (!props.denominator || props.denominator <= 0) return "";
  return `${((value / props.denominator) * 100).toFixed(1)}%`;
}
</script>

<template>
  <!-- Single 4-row × N-col grid so percentages, bar tops, counts, and labels
       all align horizontally regardless of label wrapping or bar height.
       grid-auto-flow: column lets us emit pct/bar/count/label in source
       order per bucket and have each one drop into the right row. -->
  <div class="vbars" :style="{ gridTemplateColumns: `repeat(${buckets.length}, minmax(0, 1fr))` }">
    <template v-for="bucket in buckets" :key="bucket.label">
      <div class="vbars__pct">{{ pctLabel(bucket.value) }}</div>
      <div class="vbars__bar-area">
        <div
          class="vbars__bar"
          :style="{
            height: `${(bucket.value / max) * 100}%`,
            backgroundColor: bucket.color ?? 'var(--color-poppy)',
          }"
          :aria-label="`${bucket.label}: ${bucket.value.toLocaleString()}`"
        />
      </div>
      <div class="vbars__count">{{ bucket.value.toLocaleString() }}</div>
      <div class="vbars__label">{{ bucket.label }}</div>
    </template>
  </div>
</template>

<style scoped>
.vbars {
  display: grid;
  grid-template-rows: auto 140px auto 1fr;
  grid-auto-flow: column;
  column-gap: var(--space-2);
  row-gap: var(--space-1);
  width: 100%;
}

.vbars__pct {
  align-self: end;
  text-align: center;
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
  color: var(--color-ink-muted);
}

.vbars__bar-area {
  display: flex;
  align-items: end;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.vbars__bar {
  width: 80%;
  min-height: 2px;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
}

.vbars__count {
  text-align: center;
  font-size: var(--fs-sm);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-ink);
}

.vbars__label {
  align-self: start;
  text-align: center;
  font-size: var(--fs-xs);
  color: var(--color-ink-muted);
  line-height: 1.25;
  hyphens: auto;
  word-break: break-word;
}

@media (max-width: 480px) {
  .vbars {
    grid-template-rows: auto 110px auto 1fr;
  }
  .vbars__label {
    font-size: 0.7rem;
  }
}
</style>
