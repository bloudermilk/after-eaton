<script setup lang="ts">
import { computed } from "vue";

import StatCard from "@/components/StatCard.vue";
import InfoButton from "@/components/InfoButton.vue";
import BigNumber from "@/components/charts/BigNumber.vue";
import MetricList from "@/components/charts/MetricList.vue";
import VerticalBars from "@/components/charts/VerticalBars.vue";
import ParcelMap from "@/components/map/ParcelMap.vue";
import { useDataset } from "@/composables/useDataset";
import { useMapSelection } from "@/composables/useMapSelection";
import { useParcels } from "@/composables/useParcels";
import { DATA_PATHS, REPO_URL } from "@/constants";
import { getMetric } from "@/metrics";

const { summary, generatedAt } = useDataset();
const { parcels } = useParcels();
const { activeMetricId, activeBucketKey, toggleMetric, selectBucket } = useMapSelection();

// Build a metric's display buckets from summary.json counts, dropping empty
// ones (a 0-count bucket has nothing to select on the map). Colors + keys come
// from the shared metric definition, so the cards and map never diverge.
function bucketsFor(metricId: string) {
  const s = summary.value;
  const metric = getMetric(metricId);
  if (!s || !metric) return [];
  return metric.buckets
    .map((b) => ({ key: b.key, label: b.label, value: s[b.summaryKey], color: b.color }))
    .filter((b) => b.value > 0);
}

const sfrBuckets = computed(() => bucketsFor("sfr_size"));
const lflItems = computed(() => bucketsFor("lfl"));
const aduItems = computed(() => bucketsFor("adu"));

const dwellingDenominator = computed(() => summary.value?.dwelling_rebuild_count ?? 0);
// Like-for-like percentages are of all permitted parcels (the bucket total).
const lflDenominator = computed(() => lflItems.value.reduce((sum, b) => sum + b.value, 0));

// State-bill pathway colors, pulled from the shared metric def so the paired
// SB-9 / SB-1123 numbers stay in lockstep with their map dots.
const densityBuckets = getMetric("density")?.buckets ?? [];
const sb9Color = densityBuckets.find((b) => b.key === "sb9")?.color;
const sb1123Color = densityBuckets.find((b) => b.key === "sb1123")?.color;

// The selected bucket for a card is only meaningful while that card's metric
// is the active one.
function selectedFor(metricId: string): string | null {
  return activeMetricId.value === metricId ? activeBucketKey.value : null;
}

// Any tap on a card brings it fully into view (centered, matching the mobile
// snap). This runs alongside — not instead of — the header-toggle / bucket
// selection, and is effectively a no-op on desktop where cards are already
// fully visible in the vertical rail.
function centerCardOnTap(event: MouseEvent): void {
  (event.currentTarget as HTMLElement).scrollIntoView({
    behavior: "smooth",
    inline: "center",
    block: "nearest",
  });
}

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
  <main v-if="summary" class="home">
    <div class="home__rail">
      <div class="home__intro">
        <h1>Rebuilding Altadena</h1>
        <p>
          A living analysis of how Altadena is rebuilding after the Eaton Fire of 2025. Tap a metric
          to map it; tap a bucket to isolate it.
        </p>
        <p v-if="dataAsOfLabel" class="home__pill">Data as of {{ dataAsOfLabel }}</p>
      </div>

      <StatCard
        title="Relative size"
        subtitle="Post-fire SFR vs. pre-fire SFR"
        interactive
        :active="activeMetricId === 'sfr_size'"
        class="home__card"
        @click="centerCardOnTap"
        @toggle="toggleMetric('sfr_size')"
      >
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
        <VerticalBars
          :buckets="sfrBuckets"
          :denominator="dwellingDenominator"
          :selected-bucket="selectedFor('sfr_size')"
          @select="(key) => selectBucket('sfr_size', key)"
        />
      </StatCard>

      <StatCard
        title="Like-for-like"
        subtitle="Rebuild project type"
        interactive
        :active="activeMetricId === 'lfl'"
        class="home__card"
        @click="centerCardOnTap"
        @toggle="toggleMetric('lfl')"
      >
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
        <MetricList
          :items="lflItems"
          :denominator="lflDenominator"
          :selected-bucket="selectedFor('lfl')"
          @select="(key) => selectBucket('lfl', key)"
        />
      </StatCard>

      <StatCard
        title="Accessory dwellings"
        subtitle="ADUs added relative to pre-fire"
        interactive
        :active="activeMetricId === 'adu'"
        class="home__card"
        @click="centerCardOnTap"
        @toggle="toggleMetric('adu')"
      >
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
        <MetricList
          :items="aduItems"
          :denominator="dwellingDenominator"
          :selected-bucket="selectedFor('adu')"
          @select="(key) => selectBucket('adu', key)"
        />
      </StatCard>

      <StatCard
        title="Density projects"
        subtitle="Parcels filing under state bills"
        interactive
        :active="activeMetricId === 'density'"
        class="home__card"
        @click="centerCardOnTap"
        @toggle="toggleMetric('density')"
      >
        <template #info>
          <InfoButton title="Density projects">
            <p>
              California's <strong>SB-9</strong> (effective 2022) allows residential lots to be
              split and rebuilt with up to two units per resulting parcel. <strong>SB 1123</strong>
              (effective 2025) lets owners of single-family-zoned vacant lots create up to 10
              small-lot subdivisions through a ministerial process.
            </p>
            <p>
              The two pathways are mutually exclusive — a parcel uses one or the other. Each count
              is parcels whose post-fire EPIC-LA records mention that bill in
              <code>DESCRIPTION</code>, <code>PROJECT_NAME</code>, or <code>PROJECTNAME</code>. If a
              parcel's records cite both, the most-recent mention wins (and the disagreement is
              logged for review).
            </p>
          </InfoButton>
        </template>
        <div class="paired-numbers">
          <BigNumber
            :value="summary.sb9_count"
            label="SB 9"
            bucket-key="sb9"
            :color="sb9Color"
            :selected-bucket="selectedFor('density')"
            @select="(key) => selectBucket('density', key)"
          />
          <BigNumber
            :value="summary.sb1123_count"
            label="SB 1123"
            bucket-key="sb1123"
            :color="sb1123Color"
            :selected-bucket="selectedFor('density')"
            @select="(key) => selectBucket('density', key)"
          />
        </div>
      </StatCard>

      <div class="home__meta">
        <p class="home__about">
          <strong>Altadata</strong> is free and open source. Built by Altadenans, for Altadena.
          <a :href="REPO_URL" target="_blank" rel="noopener">View source on GitHub</a>.
        </p>
        <nav class="home__links" aria-label="Site">
          <RouterLink to="/methodology">Methodology</RouterLink>
          <RouterLink to="/quality-control">Quality Control</RouterLink>
          <a :href="DATA_PATHS.parcelsCsv" download>Download parcels.csv</a>
        </nav>
      </div>
    </div>

    <div class="home__map">
      <ParcelMap
        :geojson="parcels"
        :active-metric-id="activeMetricId"
        :active-bucket="activeBucketKey"
      />
    </div>
  </main>
</template>

<style scoped>
/* Full-viewport split that overrides the global centered `main`. */
.home {
  max-width: none;
  margin: 0;
  padding: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* --- The cards rail ------------------------------------------------------ */
/* Narrow / portrait: a horizontal scroller of cards, ~31% of the viewport. */
.home__rail {
  flex: 0 0 31vh;
  display: flex;
  flex-direction: row;
  gap: var(--space-4);
  padding: var(--space-4);
  overflow-x: auto;
  overflow-y: hidden;
  background: var(--color-paper-deep);
  /* Rail sits at the bottom on mobile, so the divider is on its top edge. */
  border-top: 1px solid var(--color-rule);
  scroll-snap-type: x mandatory;
}

.home__rail :deep(.stat-card) {
  flex: 0 0 84%;
  /* Center each card so middle cards show an equal peek of their neighbors. */
  scroll-snap-align: center;
}

/* Intro + meta only show in the wide vertical rail; the narrow row is cards. */
.home__intro,
.home__meta {
  display: none;
}

.home__map {
  flex: 1;
  min-height: 0;
  position: relative;
  /* Mobile: map on top, cards rail below it. */
  order: -1;
}

/* --- Wide / landscape: vertical column on the left, map on the right ----- */
@media (min-width: 768px) {
  .home {
    flex-direction: row;
  }

  .home__rail {
    flex: 0 0 400px;
    flex-direction: column;
    max-width: 40%;
    overflow-x: hidden;
    overflow-y: auto;
    border-top: none;
    border-right: 1px solid var(--color-rule);
    scroll-snap-type: none;
  }

  /* Restore natural order: rail on the left, map on the right. */
  .home__map {
    order: 0;
  }

  .home__rail :deep(.stat-card) {
    flex: 0 0 auto;
    width: 100%;
  }

  .home__intro,
  .home__meta {
    display: block;
  }

  .home__intro h1 {
    font-size: var(--fs-xl);
    margin-bottom: var(--space-2);
  }
  .home__intro p {
    color: var(--color-ink-muted);
    font-size: var(--fs-sm);
    margin: var(--space-2) 0;
  }
}

/* Side-by-side state-bill counts (SB-9 / SB-1123) inside the density card. */
.paired-numbers {
  display: flex;
  flex-direction: row;
  gap: var(--space-4);
  width: 100%;
}

/* "Data as of" pill, now sitting just under the intro heading. */
.home__pill {
  display: inline-block;
  background: var(--color-paper);
  border: 1px solid var(--color-rule);
  padding: var(--space-2) var(--space-3);
  border-radius: 999px;
  font-size: var(--fs-xs);
  margin: var(--space-3) 0 0;
}

/* --- Rail meta (folded-in footer) --------------------------------------- */
.home__meta {
  margin-top: auto;
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-rule);
}

.home__about {
  color: var(--color-ink-muted);
  font-size: var(--fs-sm);
  margin: 0 0 var(--space-3);
}
.home__about strong {
  color: var(--color-ink);
}

.home__links {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--fs-sm);
}
</style>
