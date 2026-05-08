import sys
import copy
import resource
import time
import json
import dataclasses
import os
import subprocess

import awkward as ak
import correctionlib
import hist
import numpy as np
from coffea import processor
from coffea.analysis_tools import PackedSelection
from coffea.nanoevents import NanoAODSchema, NanoEventsFactory
from coffea.nanoevents.mapping import BufferCache
from numcodecs import Blosc
import rich
import zict

NanoAODSchema.warn_missing_crossrefs = False

# nentries = 1344000
FNAME = "root://eospublic.cern.ch//eos/opendata/cms/mc/RunIISummer20UL16NanoAODv9/TTToHadronic_TuneCP5_13TeV-powheg-pythia8/NANOAODSIM/106X_mcRun2_asymptotic_v17-v1/130000/009086DB-1E42-7545-9A35-1433EC89D04B.root"

# FROM: https://github.com/ikrommyd/virtual-array-agc/blob/main/utils/config.py#L60-L89
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
    # normal distribution with 5% variations, shape matches jets
    counts = ak.num(pt)
    pt_flat = ak.flatten(pt)
    resolution_variation = np.random.normal(np.ones_like(pt_flat), 0.05)
    return ak.unflatten(resolution_variation, counts)


class TtbarAnalysis(processor.ProcessorABC):
    def __init__(self):
        # initialize dictionary of hists for signal and control region
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

        self.cset = correctionlib.CorrectionSet.from_file("./data/corrections.json")

    def process(self, events):
        # create copies of histogram objects
        hist_dict = copy.deepcopy(self.hist_dict)

        process = events.metadata["process"]  # "ttbar" etc.
        variation = events.metadata["variation"]  # "nominal" etc.

        # normalization for MC
        x_sec = events.metadata["xsec"]
        nevts_total = events.metadata["nevts"]
        lumi = 3378  # /pb
        if process != "data":
            xsec_weight = x_sec * lumi / nevts_total
        else:
            xsec_weight = 1

        # touch additional fields
        for field in additional_fields_to_touch:
            ak.materialize(events[field])

        #### systematics
        # jet energy scale / resolution systematics
        # need to adjust schema to instead use coffea add_systematic feature, especially for ServiceX
        # cannot attach pT variations to events.jet, so attach to events directly
        # and subsequently scale pT by these scale factors
        events["pt_scale_up"] = 1.03
        events["pt_res_up"] = jet_pt_resolution(events.Jet.pt)

        syst_variations = ["nominal"]
        jet_kinematic_systs = ["pt_scale_up", "pt_res_up"]
        event_systs = [f"btag_var_{i}" for i in range(4)]
        if process == "wjets":
            event_systs.append("scale_var")

        # Only do systematics for nominal samples, e.g. ttbar__nominal
        if variation == "nominal":
            syst_variations.extend(jet_kinematic_systs)
            syst_variations.extend(event_systs)

        # for pt_var in pt_variations:
        for syst_var in syst_variations:
            ### event selection
            # very very loosely based on https://arxiv.org/abs/2006.13076

            # Note: This creates new objects, distinct from those in the 'events' object
            elecs = events.Electron
            muons = events.Muon
            jets = events.Jet
            if syst_var in jet_kinematic_systs:
                # Replace jet.pt with the adjusted values
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

            # Only keep objects that pass our requirements
            elecs = elecs[electron_reqs]
            muons = muons[muon_reqs]
            jets = jets[jet_reqs]

            B_TAG_THRESHOLD = 0.5

            ######### Store boolean masks with PackedSelection ##########
            selections = PackedSelection(dtype="uint64")
            # Basic selection criteria
            selections.add("exactly_1l", (ak.num(elecs) + ak.num(muons)) == 1)
            selections.add("atleast_4j", ak.num(jets) >= 4)
            selections.add(
                "exactly_1b", ak.sum(jets.btagCSVV2 > B_TAG_THRESHOLD, axis=1) == 1
            )
            selections.add(
                "atleast_2b", ak.sum(jets.btagCSVV2 > B_TAG_THRESHOLD, axis=1) >= 2
            )
            # Complex selection criteria
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
                    # reconstruct hadronic top as bjj system with largest pT
                    trijet = ak.combinations(
                        region_jets, 3, fields=["j1", "j2", "j3"]
                    )  # trijet candidates
                    trijet["p4"] = (
                        trijet.j1 + trijet.j2 + trijet.j3
                    )  # calculate four-momentum of tri-jet system
                    trijet["max_btag"] = np.maximum(
                        trijet.j1.btagCSVV2,
                        np.maximum(trijet.j2.btagCSVV2, trijet.j3.btagCSVV2),
                    )
                    trijet = trijet[
                        trijet.max_btag > B_TAG_THRESHOLD
                    ]  # at least one-btag in trijet candidates
                    # pick trijet candidate with largest pT and calculate mass of system
                    trijet_mass = trijet["p4"][
                        ak.argmax(trijet.p4.pt, axis=1, keepdims=True)
                    ].mass
                    observable = ak.flatten(trijet_mass)

                    if sum(region_selection) == 0:
                        continue

                syst_var_name = f"{syst_var}"
                # Break up the filling into event weight systematics and object variation systematics
                if syst_var in event_systs:
                    for i_dir, direction in enumerate(["up", "down"]):
                        # Should be an event weight systematic with an up/down variation
                        if syst_var.startswith("btag_var"):
                            i_jet = int(syst_var.rsplit("_", 1)[-1])  # Kind of fragile
                            wgt_variation = self.cset["event_systematics"].evaluate(
                                "btag_var", direction, region_jets.pt[:, i_jet]
                            )
                        elif syst_var == "scale_var":
                            # The pt array is only used to make sure the output array has the correct shape
                            wgt_variation = self.cset["event_systematics"].evaluate(
                                "scale_var", direction, region_jets.pt[:, 0]
                            )
                        syst_var_name = f"{syst_var}_{direction}"
                        hist_dict[region].fill(
                            observable=observable,
                            process=process,
                            variation=syst_var_name,
                            weight=region_weights * wgt_variation,
                        )
                else:
                    # Should either be 'nominal' or an object variation systematic
                    if variation != "nominal":
                        # This is a 2-point systematic, e.g. ttbar__scaledown, ttbar__ME_var, etc.
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


def make_events(file, buffer_cache, entry_stop):
    access_log = []
    events = NanoEventsFactory.from_root(
        {file: "Events"},
        mode="virtual",
        schemaclass=NanoAODSchema,
        buffer_cache=buffer_cache,
        access_log=access_log,
        entry_stop=entry_stop,
        metadata={
            "process": "ttbar",
            "variation": "nominal",
            "xsec": 831.76,
            "nevts": entry_stop,
        },
    ).events()
    return events, access_log


@dataclasses.dataclass
class BenchmarkResult:
    execution_time: float
    events_per_second: float
    touched: dict
    branches: list
    peak_rss: float



if __name__ == "__main__":
    CMD = ["pixi", "run"]

    # first time, download some files
    if not os.path.exists("data/input.root"):
        print("Downloading input file to data/input.root...")
        subprocess.run(CMD + ["xrdcp", FNAME, "./data/input.root"], check=True)

    if not os.path.exists("data/corrections.json"):
        print("Downloading corrections file...")
        subprocess.run(
            CMD
            + [
                "wget",
                "https://raw.githubusercontent.com/ikrommyd/virtual-array-agc/refs/heads/main/corrections.json",
                "-O",
                "./data/corrections.json",
            ],
            check=True,
        )

    # Start measurements
    assert len(sys.argv[1:]) == 3, (
        "This benchmark only accepts three arguments: cache type, codec, entry_stop"
    )

    cache_type = sys.argv[1]
    codec_type = sys.argv[2]
    entry_stop = int(sys.argv[3])

    match cache_type:
        case "inmemory":
            cache = {}
        case "inmemory_lru_100MiB":
            cache = zict.LRU(
                n=100 * (1024**2),  # 100 MiB max size
                d={},
                weight=lambda k, v: len(v),
            )
        case "inmemory_lru_500MiB":
            cache = zict.LRU(
                n=500 * (1024**2),  # 500 MiB max size
                d={},
                weight=lambda k, v: len(v),
            )
        case "ondisk":
            if os.path.exists("./cache_dir"):
                print("Clearing existing cache directory...")
                for f in os.listdir("./cache_dir"):
                    os.remove(os.path.join("./cache_dir", f))
            cache = zict.File("./cache_dir")
        case _:
            raise ValueError(f"Unknown cache type: {cache_type}")

    match codec_type:
        case "blosc":
            codec = Blosc("zstd", clevel=1, shuffle=Blosc.BITSHUFFLE)
        case "none":
            codec = None
        case _:
            raise ValueError(f"Unknown codec choice: {codec_type}")

    result_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "agc")
    os.makedirs(result_base, exist_ok=True)
    result_json = f"{result_base}/{cache_type}_{codec_type}_{entry_stop}.json"

    buffer_cache = BufferCache(cache=cache, codec=codec)
    events, access_log = make_events(
        "./data/input.root", buffer_cache, entry_stop=entry_stop
    )

    processor_instance = TtbarAnalysis()

    t0 = time.monotonic()
    out = processor_instance.process(events)
    exec_time = time.monotonic() - t0
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    def _raw_bytes(v):
        return v.nbytes if hasattr(v, "nbytes") else len(v)

    touched = {a.buffer_key: _raw_bytes(cache.get(a.buffer_key, [])) for a in access_log}
    result = BenchmarkResult(
        execution_time=exec_time,
        events_per_second=out["nevents"] / exec_time,
        touched=touched,
        branches=list(set(a.branch for a in access_log)),
        peak_rss=peak_rss,
    )

    rich.print(result)

    with open(result_json, "w") as f:
        json.dump(dataclasses.asdict(result), f, indent=4)
