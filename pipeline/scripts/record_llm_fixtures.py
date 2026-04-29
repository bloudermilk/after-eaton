"""One-off: record LLM extraction fixtures for the four QA AINs.

Run from the pipeline directory:
    .venv/bin/python scripts/record_llm_fixtures.py

Hits the live OpenRouter API. Saves one JSON per AIN under
``tests/fixtures/llm/`` capturing the rendered user prompt, the raw
LLM response, and the parsed structures so future replay-tests can use
them without network access.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from after_eaton.processing.llm_extraction import (
    ExtractionCache,
    extract_structures,
)
from after_eaton.processing.llm_prompts import (
    SYSTEM_PROMPT,
    ParcelContext,
    render_user_prompt,
)
from after_eaton.processing.llm_provider import OpenRouterProvider
from after_eaton.sources.schemas import EpicCase

QA_AINS = ["5841026011", "5828018010", "5845014011", "5845016021"]
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "llm"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _is_qualifying(rec: dict[str, object]) -> bool:
    module = rec.get("MODULENAME")
    workclass = rec.get("WORKCLASS_NAME")
    if module == "PermitManagement" and workclass in {"New", "Rebuild Project"}:
        return True
    if module == "PlanManagement" and workclass == "Rebuild":
        return True
    return False


def _is_fire(rec: dict[str, object]) -> bool:
    if rec.get("DISASTER_TYPE") == "Eaton Fire (01-2025)":
        return True
    desc = rec.get("DESCRIPTION") or ""
    return isinstance(desc, str) and "eaton" in desc.lower()


def _pre_fire_summary(din: dict[str, object]) -> str:
    use = (din.get("UseDescription") or "").strip().lower() if din.get("UseDescription") else ""
    is_single = use == "single"
    sfr_sqfts: list[float] = []
    adu_sqfts: list[float] = []
    mfr_sqfts: list[float] = []
    for slot in range(1, 6):
        design = din.get(f"DesignType{slot}")
        sqft = din.get(f"SQFTmain{slot}")
        if not design:
            continue
        prefix = str(design)[:2]
        sqft_val = float(sqft) if isinstance(sqft, (int, float)) else 0.0
        if prefix == "01":
            if slot == 1:
                sfr_sqfts.append(sqft_val)
            elif is_single:
                adu_sqfts.append(sqft_val)
            else:
                sfr_sqfts.append(sqft_val)
        elif prefix in {"02", "03", "04", "05"}:
            mfr_sqfts.append(sqft_val)
    parts: list[str] = []
    if sfr_sqfts:
        parts.append(f"{len(sfr_sqfts)} SFR ({int(sum(sfr_sqfts))} SF total)")
    if adu_sqfts:
        parts.append(f"{len(adu_sqfts)} ADU ({int(sum(adu_sqfts))} SF total)")
    if mfr_sqfts:
        parts.append(f"{len(mfr_sqfts)} MFR ({int(sum(mfr_sqfts))} SF total)")
    return ", ".join(parts) if parts else "(none recorded)"


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    epicla = json.loads((DATA_DIR / "source-epicla.json").read_text())
    dins = json.loads((DATA_DIR / "source-dins.json").read_text())

    by_ain: dict[str, list[dict[str, object]]] = defaultdict(list)
    for rec in epicla["records"]:
        by_ain[rec["MAIN_AIN"]].append(rec)

    dins_by_ain: dict[str, dict[str, object]] = {}
    for rec in dins["records"]:
        dins_by_ain[rec["AIN_1"]] = rec

    provider = OpenRouterProvider()
    cache = ExtractionCache()

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for ain in QA_AINS:
        cases = by_ain.get(ain, [])
        din = dins_by_ain.get(ain, {})
        qualifying = [c for c in cases if _is_qualifying(c) and _is_fire(c)]
        ctx = ParcelContext(
            ain=ain,
            address=str(din.get("SitusFullAddress") or din.get("SitusAddress") or ""),
            damage=str(din.get("DAMAGE_1") or ""),
            pre_fire_summary=_pre_fire_summary(din),
        )
        records: list[EpicCase] = qualifying  # type: ignore[assignment]
        print(f"=== AIN {ain} ({len(records)} qualifying records) ===")
        if not records:
            print("  no qualifying records — skipping")
            continue
        user_prompt = render_user_prompt(ctx, records)
        extraction = extract_structures(
            ctx, records, provider=provider, cache=cache
        )
        if extraction is None:
            print("  extraction failed")
            continue
        for s in extraction.structures:
            print(f"  {s.struct_type}: sqft={s.sqft}, conf={s.confidence}")
        print(f"  reasoning: {extraction.reasoning}")
        out = {
            "ain": ain,
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "extraction": asdict(extraction),
        }
        # tuples → lists for JSON serialization
        out["extraction"]["input_case_numbers"] = list(extraction.input_case_numbers)
        out["extraction"]["structures"] = [
            {**asdict(s), "evidence_case_numbers": list(s.evidence_case_numbers)}
            for s in extraction.structures
        ]
        (FIXTURES_DIR / f"{ain}.json").write_text(json.dumps(out, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
