<script setup lang="ts">
import { computed } from "vue";

import StatCard from "@/components/StatCard.vue";
import InfoButton from "@/components/InfoButton.vue";
import BigNumber from "@/components/charts/BigNumber.vue";
import DistributionBars from "@/components/charts/DistributionBars.vue";
import DonutChart from "@/components/charts/DonutChart.vue";
import VerticalBars from "@/components/charts/VerticalBars.vue";
import { useDataset } from "@/composables/useDataset";

const { summary } = useDataset();

const sfrBuckets = computed(() => {
  const s = summary.value;
  if (!s) return [];
  return [
    {
      label: ">30% smaller",
      value: s.sfr_size_pct_smaller_over_30,
      color: "var(--color-deodara)",
    },
    {
      label: "10–30% smaller",
      value: s.sfr_size_pct_smaller_10_to_30,
      color: "var(--color-deodara-soft)",
    },
    {
      label: "±10%",
      value: s.sfr_size_pct_within_10,
      color: "var(--color-alluvial)",
    },
    {
      label: "10–30% larger",
      value: s.sfr_size_pct_larger_10_to_30,
      color: "var(--color-poppy-soft)",
    },
    {
      label: ">30% larger",
      value: s.sfr_size_pct_larger_over_30,
      color: "var(--color-poppy)",
    },
  ];
});

const lflSlices = computed(() => {
  const s = summary.value;
  if (!s) return [];
  return [
    { label: "Like-for-like", value: s.lfl_count, color: "var(--color-deodara)" },
    {
      label: "Not like-for-like",
      value: s.nlfl_count,
      color: "var(--color-poppy)",
    },
    {
      label: "Not specified",
      value: s.lfl_unknown_count,
      color: "var(--color-poppy-soft)",
    },
  ];
});

const aduBuckets = computed(() => {
  const s = summary.value;
  if (!s) return [];
  const out = [
    {
      label: "+1 ADU",
      value: s.adu_added_1_count,
      color: "var(--color-deodara)",
    },
    {
      label: "+2 ADUs",
      value: s.adu_added_2_count,
      color: "var(--color-lupin)",
    },
  ];
  if (s.adu_added_3_plus_count > 0) {
    out.push({
      label: "+3 or more",
      value: s.adu_added_3_plus_count,
      color: "var(--color-poppy)",
    });
  }
  return out;
});

const dwellingDenominator = computed(() => summary.value?.dwelling_rebuild_count ?? 0);
</script>

<template>
  <main>
    <section class="hero">
      <h1>Rebuilding Altadena</h1>
      <p>A living analysis of how Altadena is rebuilding after the Eaton Fire of 2025.</p>
    </section>

    <section v-if="summary" class="grid">
      <StatCard title="Relative size" subtitle="Post-fire SFR vs. pre-fire SFR">
        <template #info>
          <InfoButton title="Relative size">
            <p>
              Compares each rebuilt single-family residence to its pre-fire footprint. The ±10% band
              is inclusive on both ends; the 10–30% bands are exclusive at 10% and inclusive at 30%;
              the &gt;30% bands are exclusive at 30%.
            </p>
            <p>
              Pre-fire size comes from the LA County DINS structure slot; post-fire size comes from
              the parsed primary EPIC-LA permit description. Parcels missing either value are not
              bucketed. Percentages use parcels rebuilding any SFR/ADU/JADU as the denominator.
            </p>
          </InfoButton>
        </template>
        <VerticalBars :buckets="sfrBuckets" :denominator="dwellingDenominator" />
      </StatCard>

      <StatCard title="Like-for-like" subtitle="Rebuild project type">
        <template #info>
          <InfoButton title="Like-for-Like">
            <p>
              LA County categorizes rebuilds as <strong>Like-for-Like</strong> (an expedited path
              that rebuilds the same structure on the same footprint) or <strong>Custom</strong>. We
              resolve each parcel's claim from the most recent EPIC-LA permit description or project
              name.
            </p>
            <p>
              <em>Not specified</em> means the permit didn't carry a clear claim either way. Parcels
              with no permit at all are excluded from this chart.
            </p>
          </InfoButton>
        </template>
        <DonutChart :slices="lflSlices" />
      </StatCard>

      <StatCard title="Accessory dwellings" subtitle="ADUs added relative to pre-fire">
        <template #info>
          <InfoButton title="Accessory dwellings">
            <p>
              Counts parcels that, post-fire, added one or more new accessory dwelling units (ADUs)
              beyond what the parcel had before the fire. Parcels that merely rebuilt their existing
              ADU are not in any bucket.
            </p>
            <p>
              Pre-fire ADU counts come from DINS structure slots; post-fire counts come from parsed
              EPIC-LA permit descriptions. Percentages use parcels rebuilding any SFR/ADU/JADU as
              the denominator.
            </p>
          </InfoButton>
        </template>
        <DistributionBars :buckets="aduBuckets" :denominator="dwellingDenominator" />
      </StatCard>

      <StatCard title="SB-9 lot splits" subtitle="Parcels with SB-9 permits filed">
        <template #info>
          <InfoButton title="SB-9 lot splits">
            <p>
              California's SB-9 law (effective 2022) allows residential lots to be split and rebuilt
              with up to two units per resulting parcel. This counts parcels whose post-fire EPIC-LA
              permit description mentions an SB-9 unit.
            </p>
          </InfoButton>
        </template>
        <BigNumber :value="summary.sb9_count" label="Parcels" />
      </StatCard>
    </section>
  </main>
</template>

<style scoped>
.hero {
  padding: var(--space-5) 0 var(--space-7);
  max-width: 720px;
}
.hero h1 {
  font-size: var(--fs-2xl);
  margin: 0 0 var(--space-3);
}
.hero p {
  color: var(--color-ink-muted);
  font-size: var(--fs-md);
  margin: 0;
}

.grid {
  display: grid;
  gap: var(--space-5);
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}

@media (min-width: 1000px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
