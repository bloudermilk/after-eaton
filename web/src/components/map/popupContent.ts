// Builds the DOM shown inside a parcel marker's MapLibre popup. Kept as a pure
// function (DOM in, element out) so it stays testable and ParcelMap.vue only
// has to wire the click/lifecycle. Labels are pulled from metrics.ts so the
// popup never drifts from the cards/legend; values come straight off the
// compact GeoJSON feature properties.
//
// We build with createElement + textContent (never innerHTML) so the county
// address string can't inject markup.

import { epiclaSearchUrl } from "@/constants";
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

function addRow(grid: HTMLElement, label: string, value: string): void {
  grid.append(el("dt", undefined, label), el("dd", undefined, value));
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

  // New-construction funnel position (stages 3–7 → "Plans received" …
  // "Construction completed"). Stage 0 means no new-building permit has reached
  // plan check yet — the bucket-0 label ("Destroyed structure") is the funnel
  // baseline, not a per-parcel stage, so we show a clearer phrase instead.
  const stageLabel =
    props.rebuild_new_stage > 0
      ? (getMetric("rebuild_progress")?.buckets.find((b) => b.stage === props.rebuild_new_stage)
          ?.label ?? "—")
      : "No new-build permit yet";
  addRow(grid, "Rebuild stage", stageLabel);

  // Pre → post structure figures (post is null until a rebuild permit is filed).
  const sqft =
    props.pre_sfr_sqft == null && props.post_sfr_sqft == null
      ? "—"
      : `${dash(props.pre_sfr_sqft)} → ${dash(props.post_sfr_sqft)} sq ft`;
  addRow(grid, "SFR size", sqft);
  addRow(grid, "SFRs", `${dash(props.pre_sfr_count)} → ${dash(props.post_sfr_count)}`);
  addRow(grid, "ADUs", `${dash(props.pre_adu_count)} → ${dash(props.post_adu_count)}`);

  // Like-for-like — omitted when the parcel has no permit at all (bucket "none").
  const lflLabel = getMetric("lfl")?.buckets.find((b) => b.key === props.lfl_bucket)?.label;
  if (lflLabel) addRow(grid, "Like-for-like", lflLabel);

  // State-bill pathway — mutually exclusive; omitted when neither applies.
  const stateBill = props.adds_sb9 ? "SB 9" : props.adds_sb1123 ? "SB 1123" : null;
  if (stateBill) addRow(grid, "State bill", stateBill);

  root.append(grid);

  // Always link out to the parcel's EPIC-LA search (works even with no case on
  // file — it just shows the empty result set for that AIN).
  const link = el("a", "parcel-popup__link", "Look up on EPIC-LA ↗");
  link.setAttribute("href", epiclaSearchUrl(props.ain));
  link.setAttribute("target", "_blank");
  link.setAttribute("rel", "noopener noreferrer");
  root.append(link);

  return root;
}
