<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import StatCard from "@/components/StatCard.vue";
import InfoButton from "@/components/InfoButton.vue";
import BigNumber from "@/components/charts/BigNumber.vue";
import MetricList from "@/components/charts/MetricList.vue";
import VerticalBars from "@/components/charts/VerticalBars.vue";
import ParcelMap from "@/components/map/ParcelMap.vue";
import { useDataset } from "@/composables/useDataset";
import { useMapSelection } from "@/composables/useMapSelection";
import { useParcels } from "@/composables/useParcels";
import { getMetric } from "@/metrics";

const { summary } = useDataset();
const { parcels } = useParcels();
const { filterSet, focusedMetricId, selectedBucketsFor, toggleMetric, selectBucket } =
  useMapSelection();

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

// Rebuild progress: the two groups partition the Destroyed/Damaged population,
// so their sum is the denominator (== summary.bsd_red_or_yellow_count) and the
// percentages read as a share of 100% — same pattern as Like-for-like below.
const rebuildProgressBuckets = computed(() => bucketsFor("rebuild_progress"));
const rebuildProgressDenominator = computed(() =>
  rebuildProgressBuckets.value.reduce((sum, b) => sum + b.value, 0),
);

const rebuildItems = computed(() => bucketsFor("new_construction"));
// The funnel's first bucket, "Plans received" (rebuild_new_plans_received_parcels),
// is the 100% baseline; every later milestone's percentage is a share of it.
const plansReceivedDenominator = computed(
  () => summary.value?.rebuild_new_plans_received_parcels ?? 0,
);
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

// Property sales — post-fire buyers split by class. The denominator is all
// post-fire sales on destroyed/damaged parcels, so each class reads as its share
// of who bought. Listings — active listings split by time on market, a share of
// all active listings. Both from RentCast, scoped to the Destroyed/Damaged set.
const propertySalesItems = computed(() => bucketsFor("property_sales"));
const propertySoldDenominator = computed(() => summary.value?.property_sold_post_fire_count ?? 0);
const listingItems = computed(() => bucketsFor("listings"));
const listingDenominator = computed(() => summary.value?.property_active_listing_count ?? 0);

// A card shows the accent border when it's the focused metric (its ramp colors
// the map) or when it has any bucket in the filter set (a participating metric).
function isCardActive(metricId: string): boolean {
  return focusedMetricId.value === metricId || selectedBucketsFor(metricId).length > 0;
}

// Tap behavior for the mobile rail. A tap on an off-center (partially obscured)
// card is a single, unambiguous "bring this metric forward" gesture: it
// activates the whole metric and scrolls the card to center, swallowing the
// bucket-select / info-open / header-toggle tap that happened to land on the
// obscured card. Once a card is centered (it is the focused metric), taps fall
// through untouched so the user can drill into buckets or open the info panel.
//
// Runs in the capture phase so it can intercept the inner button clicks before
// they fire. A no-op on desktop, where every card is fully visible in the
// vertical rail and direct interaction is already unambiguous.
function onCardTap(metricId: string, event: MouseEvent): void {
  if (!window.matchMedia("(max-width: 767.98px)").matches) return;
  // The focused metric is the centered, fully-visible card — let taps act on it.
  if (focusedMetricId.value === metricId) return;
  event.stopPropagation();
  event.preventDefault();
  toggleMetric(metricId);
  (event.currentTarget as HTMLElement).scrollIntoView({
    behavior: "smooth",
    inline: "center",
    block: "nearest",
  });
}

// On mobile the rail is a horizontal snap carousel. As the user swipes (or taps,
// via centerCardOnTap above), focus the metric of whichever card lands in the
// center so the map tracks the card you're looking at. Guarded to the mobile
// breakpoint — the desktop rail is a vertical column where this makes no sense.
const railEl = ref<HTMLElement | null>(null);
let scrollSettleTimer: ReturnType<typeof setTimeout> | undefined;

function selectCenteredCard(): void {
  const rail = railEl.value;
  if (!rail || !window.matchMedia("(max-width: 767.98px)").matches) return;
  const railCenter = rail.scrollLeft + rail.clientWidth / 2;
  let closestId: string | undefined;
  let closestDist = Infinity;
  for (const card of rail.querySelectorAll<HTMLElement>("[data-metric-id]")) {
    const dist = Math.abs(card.offsetLeft + card.offsetWidth / 2 - railCenter);
    if (dist < closestDist) {
      closestDist = dist;
      closestId = card.dataset.metricId;
    }
  }
  // Only switch on a genuine change of card — settling back on the focused card
  // must not call toggleMetric, which would wipe its bucket selection.
  if (closestId && closestId !== focusedMetricId.value) toggleMetric(closestId);
}

function onRailScroll(): void {
  clearTimeout(scrollSettleTimer);
  scrollSettleTimer = setTimeout(selectCenteredCard, 120);
}

onMounted(() => railEl.value?.addEventListener("scroll", onRailScroll, { passive: true }));
onBeforeUnmount(() => {
  railEl.value?.removeEventListener("scroll", onRailScroll);
  clearTimeout(scrollSettleTimer);
});
</script>

<template>
  <main v-if="summary" class="home">
    <div ref="railEl" class="home__rail">
      <StatCard
        title="Rebuild progress"
        subtitle="Damaged or destroyed parcels"
        interactive
        :active="isCardActive('rebuild_progress')"
        class="home__card"
        data-metric-id="rebuild_progress"
        @click.capture="onCardTap('rebuild_progress', $event)"
        @toggle="(additive) => toggleMetric('rebuild_progress', additive)"
      >
        <template #info>
          <InfoButton title="Rebuild progress">
            <p>
              Of the parcels LA County tags as <strong>destroyed or damaged</strong> in its
              post-fire Safety Assessment (Red- or Yellow-tagged), how many have started rebuilding?
              This is the County's official "Destroyed/Damaged Parcels" population.
            </p>
            <p>
              <strong>Rebuilding</strong> means the parcel has at least one active rebuild case on
              file with the county (EPIC-LA), in any stage — from a freshly filed application
              through completed construction. <strong>Not started</strong> means no active case
              exists yet. Cases the county has voided, cancelled, withdrawn, or otherwise marked
              dead don't count.
            </p>
            <p>
              The two groups are mutually exclusive and together make up every destroyed/damaged
              parcel, so the percentages are each group's share of that whole.
            </p>
          </InfoButton>
        </template>
        <VerticalBars
          :buckets="rebuildProgressBuckets"
          :denominator="rebuildProgressDenominator"
          :selected-buckets="selectedBucketsFor('rebuild_progress')"
          @select="(key, additive) => selectBucket('rebuild_progress', key, additive)"
        />
      </StatCard>

      <StatCard
        v-if="false"
        title="New construction"
        subtitle="Rebuild milestones"
        interactive
        :active="isCardActive('new_construction')"
        class="home__card"
        data-metric-id="new_construction"
        @click.capture="onCardTap('new_construction', $event)"
        @toggle="(additive) => toggleMetric('new_construction', additive)"
      >
        <template #info>
          <InfoButton title="New construction">
            <p>
              This funnel tracks <strong>new construction</strong> only — homes being rebuilt from
              the ground up. It follows EPIC-LA's new-building permits and deliberately excludes
              repairs, additions, retrofits, and retaining walls, so every milestone reflects a
              from-scratch rebuild rather than work on a structure still standing.
            </p>
            <p>
              <strong>Plans received</strong> is the baseline (100%): every parcel in the fire area
              whose new-building permit has reached plan check. Each milestone below is the share of
              those parcels that has progressed further. The funnel starts here — a new-building
              permit doesn't exist during the earlier application and zoning steps (those happen on
              a separate rebuild record), and we'll cover them in a future funnel.
            </p>
            <p>
              We report it <strong>cumulatively</strong>: a parcel is counted at every stage up to
              the furthest one its new-build permit reached, so the counts decline at each later
              stage. A parcel's map dot is colored by that furthest stage.
            </p>
            <p>
              <strong>On the map:</strong> by default every parcel that reached Plans received is
              shown, colored by the furthest stage it has reached. Tapping a row narrows the map to
              the parcels <em>currently at</em> that stage — so they share one color, and fewer dots
              light up than the row's cumulative count.
            </p>
          </InfoButton>
        </template>
        <MetricList
          :items="rebuildItems"
          :denominator="plansReceivedDenominator"
          :selected-buckets="selectedBucketsFor('new_construction')"
          @select="(key, additive) => selectBucket('new_construction', key, additive)"
        />
      </StatCard>

      <StatCard
        title="Relative size"
        subtitle="Post-fire SFR vs. pre-fire SFR"
        interactive
        :active="isCardActive('sfr_size')"
        class="home__card"
        data-metric-id="sfr_size"
        @click.capture="onCardTap('sfr_size', $event)"
        @toggle="(additive) => toggleMetric('sfr_size', additive)"
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
          :selected-buckets="selectedBucketsFor('sfr_size')"
          @select="(key, additive) => selectBucket('sfr_size', key, additive)"
        />
      </StatCard>

      <StatCard
        title="Like-for-like"
        subtitle="Rebuild project type"
        interactive
        :active="isCardActive('lfl')"
        class="home__card"
        data-metric-id="lfl"
        @click.capture="onCardTap('lfl', $event)"
        @toggle="(additive) => toggleMetric('lfl', additive)"
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
          :selected-buckets="selectedBucketsFor('lfl')"
          @select="(key, additive) => selectBucket('lfl', key, additive)"
        />
      </StatCard>

      <StatCard
        title="Accessory dwellings"
        subtitle="ADUs added relative to pre-fire"
        interactive
        :active="isCardActive('adu')"
        class="home__card"
        data-metric-id="adu"
        @click.capture="onCardTap('adu', $event)"
        @toggle="(additive) => toggleMetric('adu', additive)"
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
          :selected-buckets="selectedBucketsFor('adu')"
          @select="(key, additive) => selectBucket('adu', key, additive)"
        />
      </StatCard>

      <StatCard
        title="Density projects"
        subtitle="Parcels filing under state bills"
        interactive
        :active="isCardActive('density')"
        class="home__card"
        data-metric-id="density"
        @click.capture="onCardTap('density', $event)"
        @toggle="(additive) => toggleMetric('density', additive)"
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
            :selected-buckets="selectedBucketsFor('density')"
            @select="(key, additive) => selectBucket('density', key, additive)"
          />
          <BigNumber
            :value="summary.sb1123_count"
            label="SB 1123"
            bucket-key="sb1123"
            :color="sb1123Color"
            :selected-buckets="selectedBucketsFor('density')"
            @select="(key, additive) => selectBucket('density', key, additive)"
          />
        </div>
      </StatCard>

      <StatCard
        title="Property sales"
        subtitle="Post-fire buyers"
        interactive
        :active="isCardActive('property_sales')"
        class="home__card"
        data-metric-id="property_sales"
        @click.capture="onCardTap('property_sales', $event)"
        @toggle="(additive) => toggleMetric('property_sales', additive)"
      >
        <template #info>
          <InfoButton title="Property sales">
            <p>
              Who is buying destroyed and damaged parcels since the fire, from
              <strong>RentCast</strong>. Each parcel that changed hands after
              <strong>January 7, 2025</strong> is grouped by its new owner of record — the buyer.
            </p>
            <p>
              <strong>Individuals</strong> and <strong>Trusts</strong> are people buying in their
              own name or through a personal or family trust; <strong>Companies</strong> are LLCs,
              corporations, and other business entities — the developers and flippers. We read the
              class from the owner's name, not RentCast's owner type, which files personal trusts
              under "Organization."
            </p>
            <p>
              Percentages are each group's share of all post-fire sales on destroyed or damaged
              parcels. Tap a group to highlight those parcels on the map; open a parcel to see its
              sale date and buyer.
            </p>
          </InfoButton>
        </template>
        <MetricList
          :items="propertySalesItems"
          :denominator="propertySoldDenominator"
          :selected-buckets="selectedBucketsFor('property_sales')"
          @select="(key, additive) => selectBucket('property_sales', key, additive)"
        />
      </StatCard>

      <StatCard
        title="Listings"
        subtitle="Active listings by time on market"
        interactive
        :active="isCardActive('listings')"
        class="home__card"
        data-metric-id="listings"
        @click.capture="onCardTap('listings', $event)"
        @toggle="(additive) => toggleMetric('listings', additive)"
      >
        <template #info>
          <InfoButton title="Listings">
            <p>
              Destroyed and damaged parcels with an active for-sale listing, from
              <strong>RentCast</strong>, grouped by how long they've been on the market as of the
              latest data refresh.
            </p>
            <p>
              Percentages are each band's share of all active listings on destroyed or damaged
              parcels. A longer time on market can signal softer price or demand. Tap a band to
              highlight those parcels on the map.
            </p>
          </InfoButton>
        </template>
        <MetricList
          :items="listingItems"
          :denominator="listingDenominator"
          :selected-buckets="selectedBucketsFor('listings')"
          @select="(key, additive) => selectBucket('listings', key, additive)"
        />
      </StatCard>
    </div>

    <div class="home__map">
      <ParcelMap :geojson="parcels" :focused-metric-id="focusedMetricId" :filter-set="filterSet" />
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
  /* Anchor point for the bottom-overlay rail on mobile. */
  position: relative;
}

/* --- The cards rail ------------------------------------------------------ */
/* Narrow / portrait: a transparent overlay anchored to the bottom of the
   full-height map. Cards keep their natural height and float over the map. */
.home__rail {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1;
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  gap: var(--space-4);
  padding: var(--space-4);
  overflow-x: auto;
  overflow-y: hidden;
  background: transparent;
  scroll-snap-type: x mandatory;
  /* The rail must stay hit-testable so it can be swiped: a `pointer-events: none`
     scroll container can't be panned by touch (the swipe gesture has no target,
     which is what disabled native sliding on iOS). The map stays interactive in
     the large area above the bottom card band — the rail only ever covers that
     band, never the rest of the full-height map. */
}

.home__rail :deep(.stat-card) {
  flex: 0 0 88%;
  /* Center each card so middle cards show an equal peek of their neighbors. */
  scroll-snap-align: center;
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
    /* Restore the static left-sidebar column (resets the mobile overlay). */
    position: static;
    flex: 0 0 400px;
    flex-direction: column;
    align-items: stretch;
    max-width: 40%;
    overflow-x: hidden;
    overflow-y: auto;
    background: var(--color-paper-deep);
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
}

/* Side-by-side state-bill counts (SB-9 / SB-1123) inside the density card. */
.paired-numbers {
  display: flex;
  flex-direction: row;
  gap: var(--space-4);
  width: 100%;
}
</style>
