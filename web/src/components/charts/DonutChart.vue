<script setup lang="ts">
import { computed } from "vue";

interface Slice {
  // Map bucket key; when present the slice/legend is clickable.
  key?: string;
  label: string;
  value: number;
  color: string;
}

const props = defineProps<{
  slices: Slice[];
  // Key of the currently selected bucket (dims the others).
  selectedBucket?: string | null;
}>();

const emit = defineEmits<{ select: [key: string] }>();

const total = computed(() => props.slices.reduce((s, x) => s + x.value, 0));

interface Arc {
  key?: string;
  label: string;
  value: number;
  color: string;
  pathD: string;
}

function isDim(s: { key?: string }): boolean {
  return props.selectedBucket != null && s.key !== props.selectedBucket;
}

function onSelect(s: { key?: string }): void {
  if (s.key) emit("select", s.key);
}

// Render slices as concatenated SVG arc paths in a fixed 200x200 viewBox.
// No animation — simply compute final geometry and emit it.
const arcs = computed<Arc[]>(() => {
  const cx = 100;
  const cy = 100;
  const r = 80;
  const t = total.value;
  if (t <= 0) return [];

  let acc = 0;
  return props.slices.map((s) => {
    const startFrac = acc / t;
    const endFrac = (acc + s.value) / t;
    acc += s.value;

    const startAngle = startFrac * Math.PI * 2 - Math.PI / 2;
    const endAngle = endFrac * Math.PI * 2 - Math.PI / 2;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);
    const largeArc = endFrac - startFrac > 0.5 ? 1 : 0;

    // Two arcs join cleanly when the slice is the only one (full circle):
    // SVG arcs with identical start and end points draw nothing, so we
    // special-case that.
    let pathD: string;
    if (s.value === t) {
      pathD = `M ${cx - r} ${cy} A ${r} ${r} 0 1 1 ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx - r} ${cy} Z`;
    } else {
      pathD = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`;
    }
    return { key: s.key, label: s.label, value: s.value, color: s.color, pathD };
  });
});

function pct(value: number): string {
  if (total.value <= 0) return "0%";
  return `${Math.round((value / total.value) * 100)}%`;
}
</script>

<template>
  <div class="donut">
    <svg viewBox="0 0 200 200" class="donut__svg" aria-hidden="true">
      <g v-if="arcs.length">
        <path
          v-for="arc in arcs"
          :key="arc.label"
          :d="arc.pathD"
          :fill="arc.color"
          class="donut__arc"
          :class="{ 'is-dim': isDim(arc), 'is-clickable': !!arc.key }"
          @click="onSelect(arc)"
        />
      </g>
      <!-- inner cutout -->
      <circle cx="100" cy="100" r="46" fill="var(--color-paper)" />
    </svg>
    <ul class="donut__legend">
      <li v-for="s in slices" :key="s.label">
        <button
          type="button"
          class="donut__legend-btn"
          :class="{ 'is-dim': isDim(s), 'is-selected': s.key === selectedBucket }"
          :disabled="!s.key"
          :aria-pressed="s.key ? s.key === selectedBucket : undefined"
          @click="onSelect(s)"
        >
          <span class="donut__swatch" :style="{ backgroundColor: s.color }" aria-hidden="true" />
          <span class="donut__label">{{ s.label }}</span>
          <span class="donut__value"
            >{{ s.value.toLocaleString() }} <small>({{ pct(s.value) }})</small></span
          >
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.donut {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: var(--space-4);
  align-items: center;
  width: 100%;
}

@media (max-width: 380px) {
  .donut {
    grid-template-columns: 1fr;
    justify-items: center;
    text-align: left;
  }
  .donut__legend {
    width: 100%;
  }
}

.donut__svg {
  width: 160px;
  height: 160px;
}

.donut__legend {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--fs-sm);
}

.donut__legend li {
  display: block;
}

.donut__legend-btn {
  display: grid;
  grid-template-columns: 14px 1fr auto;
  gap: var(--space-2);
  align-items: center;
  width: 100%;
  appearance: none;
  border: 0;
  background: transparent;
  padding: var(--space-1) var(--space-2);
  margin: 0 calc(-1 * var(--space-2));
  border-radius: var(--radius-sm);
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background 0.15s ease,
    opacity 0.15s ease;
}

.donut__legend-btn:disabled {
  cursor: default;
}

.donut__legend-btn:not(:disabled):hover {
  background: var(--color-paper-deep);
}

.donut__legend-btn:focus-visible {
  outline: 2px solid var(--color-poppy);
  outline-offset: 1px;
}

.donut__legend-btn.is-selected {
  background: var(--color-paper-deep);
  box-shadow: inset 0 0 0 1px var(--color-ink);
}

.donut__arc {
  transition: opacity 0.15s ease;
}

.donut__arc.is-clickable {
  cursor: pointer;
}

.is-dim {
  opacity: 0.3;
}

.donut__swatch {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}

.donut__label {
  color: var(--color-ink-muted);
}

.donut__value {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.donut__value small {
  color: var(--color-ink-muted);
  font-weight: 400;
  margin-left: 4px;
}
</style>
