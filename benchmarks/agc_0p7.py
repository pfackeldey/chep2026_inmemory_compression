"""
AGC benchmark for coffea 0.7.x / awkward1 (no buffer cache support).

Measures peak RSS and runtime as a function of entry_stop for comparison
with coffea 2024+ which has buffer-cache based virtual arrays.
"""
import sys
import copy
import resource
import time
import json
import dataclasses
import os
import subprocess
from pathlib import Path

import awkward as ak
import correctionlib
import hist
import numpy as np
from coffea import processor
from coffea.analysis_tools import PackedSelection
from coffea.nanoevents import NanoAODSchema, NanoEventsFactory
import rich

NanoAODSchema.warn_missing_crossrefs = False

FNAME = "root://eospublic.cern.ch//eos/opendata/cms/mc/RunIISummer20UL16NanoAODv9/TTToHadronic_TuneCP5_13TeV-powheg-pythia8/NANOAODSIM/106X_mcRun2_asymptotic_v17-v1/130000/009086DB-1E42-7545-9A35-1433EC89D04B.root"

# Resolve data paths: search upward from script location for data/ directory
_SCRIPT_DIR = Path(__file__).parent.resolve()

def _find_project_root(start: Path) -> Path:
    """Walk upward until we find a data/ directory."""
    current = start
    for _ in range(5):  # Don't climb forever
        if (current / "data").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    # Fallback: assume repo root is two levels above benchmarks/
    return _SCRIPT_DIR.parent.parent

_PROJECT_ROOT = _find_project_root(_SCRIPT_DIR)
_DATA_DIR = _PROJECT_ROOT / "data"
_INPUT_ROOT = str(_DATA_DIR / "input.root")
_CORRECTIONS_JSON = str(_DATA_DIR / "corrections.json")

# Fields to explicitly touch (forces buffer reads in lazy backends)
additional_fields_to_touch = [
    "LHEPdfWeight",
    ("GenPart", "pt"),
    ("GenPart", "eta"),
    ("GenPart", "phi"),
    ("GenPart", "pdgId"),
    ("GenPart", "genPartIdxMother"),
    ("GenPart", "statusFlags"),
    ("GenPart", "mass"),
    ("LHEScaleWeight",),
    ("GenJet", "pt"),
    ("GenPart", "status"),
    ("LHEPart", "eta"),
    ("LHEPart", "phi"),
    ("LHEPart", "pt"),
    ("GenJet", "eta"),
    ("GenJet", "phi"),
    ("Jet", "eta"),
    ("Jet", "phi"),
    ("SoftActivityJet", "pt"),
    ("SoftActivityJet", "phi"),
    ("SoftActivityJet", "eta"),
    ("GenJet", "mass"),
    ("Jet", "pt"),
    ("Jet", "mass"),
    ("LHEPart", "mass"),
    ("Jet", "qgl"),
    ("Jet", "muonSubtrFactor"),
    ("Jet", "puIdDisc"),
]


def jet_pt_resolution(pt):
    counts = ak.num(pt)
    pt_flat = ak.flatten(pt)
    resolution_variation = np.random.normal(np.ones_like(pt_flat), 0.05)
    return ak.unflatten(resolution_variation, counts)


class TtbarAnalysis(processor.ProcessorABC):
    def __init__(self):
        self.hist_dict = {}
        for region in ["4j1b", "4j2b"]:
            self.hist_dict[region] = (
                hist.Hist.new.Reg(
                    25, 50, 550, name="observable", label="observable [GeV]"
                )
                .StrCat([], name="process", label="Process", growth=True)
                .StrCat([], name="variation", label="Systematic variation", growth=True)
                .Weight()
            )

        self.cset = correctionlib.CorrectionSet.from_file(_CORRECTIONS_JSON)

    def process(self, events):
        hist_dict = copy.deepcopy(self.hist_dict)

        process = events.metadata["process"]
        variation = events.metadata["variation"]

        x_sec = events.metadata["xsec"]
        nevts_total = events.metadata["nevts"]
        lumi = 3378  # /pb
        if process != "data":
            xsec_weight = x_sec * lumi / nevts_total
        else:
            xsec_weight = 1

        # touch additional fields (best-effort for awkward1)
        for field in additional_fields_to_touch:
            try:
                _ = repr(events[field])  # repr to force read/materialize
            except Exception:
                pass

        events["pt_scale_up"] = 1.03
        events["pt_res_up"] = jet_pt_resolution(events.Jet.pt)

        syst_variations = ["nominal"]
        jet_kinematic_systs = ["pt_scale_up", "pt_res_up"]
        event_systs = [f"btag_var_{i}" for i in range(4)]
        if process == "wjets":
            event_systs.append("scale_var")

        if variation == "nominal":
            syst_variations.extend(jet_kinematic_systs)
            syst_variations.extend(event_systs)

        for syst_var in syst_variations:
            elecs = events.Electron
            muons = events.Muon
            jets = events.Jet
            if syst_var in jet_kinematic_systs:
                jets["pt"] = jets.pt * events[syst_var]

            electron_reqs = (
                (elecs.pt > 30)
                & (np.abs(elecs.eta) < 2.1)
                & (elecs.cutBased == 4)
                & (elecs.sip3d < 4)
            )
            muon_reqs = (
                (muons.pt > 30)
                & (np.abs(muons.eta) < 2.1)
                & (muons.tightId)
                & (muons.sip3d < 4)
                & (muons.pfRelIso04_all < 0.15)
            )
            jet_reqs = (
                (jets.pt > 30) & (np.abs(jets.eta) < 2.4) & (jets.isTightLeptonVeto)
            )

            elecs = elecs[electron_reqs]
            muons = muons[muon_reqs]
            jets = jets[jet_reqs]

            B_TAG_THRESHOLD = 0.5

            selections = PackedSelection(dtype="uint64")
            selections.add("exactly_1l", (ak.num(elecs) + ak.num(muons)) == 1)
            selections.add("atleast_4j", ak.num(jets) >= 4)
            selections.add(
                "exactly_1b", ak.sum(jets.btagCSVV2 > B_TAG_THRESHOLD, axis=1) == 1
            )
            selections.add(
                "atleast_2b", ak.sum(jets.btagCSVV2 > B_TAG_THRESHOLD, axis=1) >= 2
            )
            selections.add(
                "4j1b", selections.all("exactly_1l", "atleast_4j", "exactly_1b")
            )
            selections.add(
                "4j2b", selections.all("exactly_1l", "atleast_4j", "atleast_2b")
            )

            for region in ["4j1b", "4j2b"]:
                region_selection = selections.all(region)
                region_jets = jets[region_selection]
                region_elecs = elecs[region_selection]
                region_muons = muons[region_selection]
                region_weights = np.ones(len(region_jets)) * xsec_weight

                if region == "4j1b":
                    observable = ak.sum(region_jets.pt, axis=-1)

                elif region == "4j2b":
                    trijet = ak.combinations(region_jets, 3, fields=["j1", "j2", "j3"])
                    trijet["p4"] = trijet.j1 + trijet.j2 + trijet.j3
                    trijet["max_btag"] = np.maximum(
                        trijet.j1.btagCSVV2,
                        np.maximum(trijet.j2.btagCSVV2, trijet.j3.btagCSVV2),
                    )
                    trijet = trijet[trijet.max_btag > B_TAG_THRESHOLD]
                    trijet_mass = trijet["p4"][
                        ak.argmax(trijet.p4.pt, axis=1, keepdims=True)
                    ].mass
                    observable = ak.flatten(trijet_mass)

                    if sum(region_selection) == 0:
                        continue

                syst_var_name = f"{syst_var}"
                if syst_var in event_systs:
                    for i_dir, direction in enumerate(["up", "down"]):
                        try:
                            if syst_var.startswith("btag_var"):
                                i_jet = int(syst_var.rsplit("_", 1)[-1])
                                wgt_variation = self.cset["event_systematics"].evaluate(
                                    "btag_var", direction, region_jets.pt[:, i_jet]
                                )
                            elif syst_var == "scale_var":
                                wgt_variation = self.cset["event_systematics"].evaluate(
                                    "scale_var", direction, region_jets.pt[:, 0]
                                )
                        except Exception:
                            wgt_variation = 1.0
                        syst_var_name = f"{syst_var}_{direction}"
                        hist_dict[region].fill(
                            observable=observable,
                            process=process,
                            variation=syst_var_name,
                            weight=region_weights * wgt_variation,
                        )
                else:
                    if variation != "nominal":
                        syst_var_name = variation
                    hist_dict[region].fill(
                        observable=observable,
                        process=process,
                        variation=syst_var_name,
                        weight=region_weights,
                    )

        output = {"nevents": len(events), "hist_dict": hist_dict}
        return output

    def postprocess(self, accumulator):
        return accumulator


@dataclasses.dataclass
class BenchmarkResult:
    execution_time: float
    events_per_second: float
    touched: dict
    branches: list
    peak_rss: float


if __name__ == "__main__":
    assert len(sys.argv[1:]) == 2, (
        "Usage: agc_0p7.py <label> <entry_stop>  (e.g. agc_0p7.py no_buffer_cache 100000)"
    )

    label = sys.argv[1]
    entry_stop = int(sys.argv[2])

    file_path = _INPUT_ROOT

    events = NanoEventsFactory.from_root(
        file_path,
        schemaclass=NanoAODSchema,
        entry_stop=entry_stop,
        metadata={
            "process": "ttbar",
            "variation": "nominal",
            "xsec": 831.76,
            "nevts": entry_stop,
        },
    ).events()

    processor_instance = TtbarAnalysis()

    t0 = time.monotonic()
    out = processor_instance.process(events)
    exec_time = time.monotonic() - t0
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    result = BenchmarkResult(
        execution_time=exec_time,
        events_per_second=out["nevents"] / exec_time,
        touched={},
        branches=[],
        peak_rss=peak_rss,
    )

    rich.print(result)

    result_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "agc")
    os.makedirs(result_base, exist_ok=True)
    result_json = f"{result_base}/coffea07_{label}_{entry_stop}.json"

    with open(result_json, "w") as f:
        json.dump(dataclasses.asdict(result), f, indent=4)
