// Builds the DOM shown inside a parcel marker's MapLibre popup. Kept as a pure
// function (DOM in, element out) so it stays testable and ParcelMap.vue only
// has to wire the click/lifecycle. Labels are pulled from metrics.ts so the
// popup never drifts from the cards/legend; values come straight off the
// compact GeoJSON feature properties.
//
// We build with createElement + textContent (never innerHTML) so the county
// address string can't inject markup.

import { assessorPortalUrl, epiclaSearchUrl } from "@/constants";
import { getMetric } from "@/metrics";
import type { ParcelProperties } from "@/types";

// FIRESCOPE %-loss buckets (DINS DAMAGE_1) → friendly labels.
const DAMAGE_LABELS: Record<string, string> = {
  destroyed: "Destroyed (>50%)",
  major: "Major (26–50%)",
  minor: "Minor (10–25%)",
  affected: "Affected (1–9%)",
  no_damage: "No damage",
  no_data: "No data",
};

// Safety-assessment tag (DINS BSD_Tag) → friendly label. "none" → no tag row.
const BSD_LABELS: Record<string, string> = {
  red: "Red-tagged",
  yellow: "Yellow-tagged",
  green: "Green-tagged",
};

function el(tag: string, className?: string, text?: string): HTMLElement {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** Count/sqft → localized string, or an em dash when unknown (null). */
function dash(value: number | null | undefined): string {
  return value == null ? "—" : value.toLocaleString();
}

/** ISO timestamp/date → its `YYYY-MM-DD` day, or null when absent. */
function isoDay(value: string | null): string | null {
  return value ? value.slice(0, 10) : null;
}

/** Price → "$1,250,000", or null when absent. */
function money(value: number | null): string | null {
  return value == null ? null : `$${value.toLocaleString()}`;
}

/** "company" → "Company". Owner-class keys are single lowercase words. */
function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function addRow(grid: HTMLElement, label: string, value: string): void {
  grid.append(el("dt", undefined, label), el("dd", undefined, value));
}

// The two earliest rebuild milestones (stages 1–2). New-building permits — and
// so the new_construction funnel card — only ever carry stages 3–7, so these
// have no card and are named here; stages 3–7 reuse the card's bucket labels
// (below) so the popup never drifts from it.
const EARLY_REBUILD_STAGES: readonly { stage: number; label: string }[] = [
  { stage: 1, label: "Application received" },
  { stage: 2, label: "Zoning cleared" },
];

/** All seven rebuild milestones as {stage, label}, in lifecycle order (1→7). */
function rebuildStageLabels(): { stage: number; label: string }[] {
  const funnel = (getMetric("new_construction")?.buckets ?? []).map((b) => ({
    stage: b.stage ?? 0,
    label: b.label,
  }));
  return [...EARLY_REBUILD_STAGES, ...funnel];
}

export function buildPopupContent(props: ParcelProperties): HTMLElement {
  const root = el("div", "parcel-popup__body");

  // Heading: address when we have one, falling back to the AIN.
  root.append(el("div", "parcel-popup__title", props.address || `AIN ${props.ain}`));
  if (props.address) root.append(el("div", "parcel-popup__ain", `AIN ${props.ain}`));

  const grid = el("dl", "parcel-popup__grid");

  // Damage + safety tag.
  const damageLabel = DAMAGE_LABELS[props.damage] ?? props.damage;
  const bsdLabel = BSD_LABELS[props.bsd_status];
  addRow(grid, "Damage", bsdLabel ? `${damageLabel} · ${bsdLabel}` : damageLabel);

  // Rebuild milestones reached, in lifecycle order. We read the ALL-workclass
  // `rebuild_stage` (0–7), not `rebuild_new_stage` (new-building only, 3–7),
  // which would miss parcels rebuilding via repair or other permits — and so
  // would show "Not started" for a parcel the map colors "Started". The funnel
  // is monotonic, so list every milestone up to the furthest reached. A
  // "Started" parcel whose active case hasn't reached even stage 1 still reads
  // "Started" rather than "Not started", staying consistent with its dot.
  const reached = rebuildStageLabels()
    .filter((s) => s.stage <= props.rebuild_stage)
    .map((s) => s.label);
  const rebuildValue = reached.length
    ? reached.join(", ")
    : props.rebuild_progress_bucket === "rebuilding"
      ? "Started"
      : "Not started";
  addRow(grid, "Rebuild", rebuildValue);

  // Pre → post structure figures (post is null until a rebuild permit is filed).
  // Counts and sizes are paired per dwelling type: SFRs then ADUs.
  const sfrSqft =
    props.pre_sfr_sqft == null && props.post_sfr_sqft == null
      ? "—"
      : `${dash(props.pre_sfr_sqft)} → ${dash(props.post_sfr_sqft)} sq ft`;
  const aduSqft =
    props.pre_adu_sqft == null && props.post_adu_sqft == null
      ? "—"
      : `${dash(props.pre_adu_sqft)} → ${dash(props.post_adu_sqft)} sq ft`;
  addRow(grid, "SFRs", `${dash(props.pre_sfr_count)} → ${dash(props.post_sfr_count)}`);
  addRow(grid, "SFRs size", sfrSqft);
  addRow(grid, "ADUs", `${dash(props.pre_adu_count)} → ${dash(props.post_adu_count)}`);
  addRow(grid, "ADUs size", aduSqft);

  // Like-for-like — omitted when the parcel has no permit at all (bucket "none").
  const lflLabel = getMetric("lfl")?.buckets.find((b) => b.key === props.lfl_bucket)?.label;
  if (lflLabel) addRow(grid, "Like-for-like", lflLabel);

  // State-bill pathway — mutually exclusive; omitted when neither applies.
  const stateBill = props.adds_sb9 ? "SB 9" : props.adds_sb1123 ? "SB 1123" : null;
  if (stateBill) addRow(grid, "State bill", stateBill);

  // Post-fire real-estate activity (RentCast) — each row omitted when absent.
  if (props.sold_post_fire && props.last_sale_date) {
    const price = money(props.last_sale_price);
    const soldDay = props.last_sale_date.slice(0, 10);
    addRow(grid, "Sold", price ? `${soldDay} · ${price}` : soldDay);
    if (props.owner_name) {
      // Derived buyer class (individual/trust/company), not RentCast's owner_type
      // — which files personal trusts under "Organization".
      const classLabel = props.owner_class ? titleCase(props.owner_class) : null;
      // User-facing label stays "Buyer" (the post-fire owner of record).
      addRow(grid, "Buyer", classLabel ? `${props.owner_name} (${classLabel})` : props.owner_name);
    }
  }
  if (props.active_listing) {
    const listedDay = isoDay(props.listing_date);
    const status = props.listing_status ? `(${props.listing_status})` : null;
    // Time-on-market band as of the last refresh, from the shared Listings metric.
    const ageLabel = getMetric("listings")?.buckets.find(
      (b) => b.key === props.listing_age_bucket,
    )?.label;
    const listedText = [
      listedDay ? `listed ${listedDay}` : null,
      ageLabel ? `${ageLabel} on market` : null,
      status,
    ]
      .filter(Boolean)
      .join(" · ");
    addRow(grid, "For sale", listedText || "Active");
  }

  root.append(grid);

  // Always link out to the parcel's EPIC-LA search (works even with no case on
  // file — it just shows the empty result set for that AIN).
  const epiclaLink = el("a", "parcel-popup__link", "Search EPIC-LA ↗");
  epiclaLink.setAttribute("href", epiclaSearchUrl(props.ain));
  epiclaLink.setAttribute("target", "_blank");
  epiclaLink.setAttribute("rel", "noopener noreferrer");
  root.append(epiclaLink);

  // Assessor portal parcel-detail page for the same AIN.
  const assessorLink = el("a", "parcel-popup__link", "Assessor Portal ↗");
  assessorLink.setAttribute("href", assessorPortalUrl(props.ain));
  assessorLink.setAttribute("target", "_blank");
  assessorLink.setAttribute("rel", "noopener noreferrer");
  root.append(assessorLink);

  return root;
}
