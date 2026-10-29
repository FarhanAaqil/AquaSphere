"""
Registry of the open satellite datasets behind the surface store (roadmap Phase 2).

Every product is served by a NOAA ERDDAP without an account, on a 0.25° daily grid. Each spec
says which ERDDAP variables fill which store variables, which mask records their availability,
and when the product starts (earlier dates stay masked rather than being filled).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    server: str
    dataset_id: str
    # store variable -> ERDDAP variable
    variables: dict[str, str]
    # store mask variable set from this dataset's first variable
    mask: str
    # extra singleton dimension between time and latitude, e.g. "[(0.0)]" for zlev
    extra_dim: str = ""
    start: str = "1981-09-01"
    title: str = ""
    citation: str = ""
    independence: str = "to-verify"  # status in the blueprint §10.1 audit
    notes: list[str] = field(default_factory=list)

    @property
    def griddap(self) -> str:
        return f"{self.server}/griddap/{self.dataset_id}"


COASTWATCH_PFEG = "https://coastwatch.pfeg.noaa.gov/erddap"
COASTWATCH_CENTRAL = "https://coastwatch.noaa.gov/erddap"

SOURCES: dict[str, DatasetSpec] = {
    "oisst": DatasetSpec(
        key="oisst",
        server=COASTWATCH_PFEG,
        dataset_id="ncdcOisst21Agg",
        variables={"sst": "sst"},
        mask="mask_sst",
        extra_dim="[(0.0)]",
        start="1981-09-01",
        title="NOAA OISST v2.1, AVHRR-only, Final, 0.25° daily",
        citation="Huang et al. (2021), J. Climate 34(8)",
        independence="verified",
        notes=["Blends ships, buoys and Argo near-surface values (above ~5 m)."],
    ),
    "ssh": DatasetSpec(
        key="ssh",
        server=COASTWATCH_PFEG,
        dataset_id="nesdisSSH1day",
        variables={"sla": "sla", "ug": "ugos", "vg": "vgos"},
        mask="mask_sla",
        start="2017-02-13",
        title="NOAA CoastWatch sea-surface height anomaly and geostrophic currents, 0.25° daily",
        citation="NOAA CoastWatch / NESDIS multi-mission altimetry",
        independence="to-verify",
        notes=["Starts 2017-02-13: altimetry channels are masked before that date."],
    ),
    "smap": DatasetSpec(
        key="smap",
        server=COASTWATCH_CENTRAL,
        dataset_id="noaacwSMAPsssDaily",
        variables={"sss": "sss"},
        mask="mask_sss",
        extra_dim="[(0.0)]",
        start="2015-04-01",
        title="SMAP sea-surface salinity, near real-time, 0.25° daily",
        citation="NOAA CoastWatch SMAP SSS",
        independence="to-verify",
        notes=["Starts 2015-04-01; coastal values are less reliable."],
    ),
    "wind": DatasetSpec(
        key="wind",
        server=COASTWATCH_CENTRAL,
        dataset_id="noaacwBlendedWindsDaily",
        variables={"u10": "u_wind", "v10": "v_wind"},
        mask="mask_wind",
        extra_dim="[(10.0)]",
        start="1987-07-09",
        title="NOAA NCEI Blended Sea Winds v2.0, science quality, 0.25° daily",
        citation="Saha & Zhang, NOAA NCEI Blended Seawinds v2",
        independence="to-verify",
    ),
}

# Preliminary (near-real-time) OISST, needed later for the E7 nowcast experiment.
OISST_PRELIMINARY = DatasetSpec(
    key="oisst_prelim",
    server=COASTWATCH_PFEG,
    dataset_id="ncdcOisst21NrtAgg",
    variables={"sst": "sst"},
    mask="mask_sst",
    extra_dim="[(0.0)]",
    title="NOAA OISST v2.1, Preliminary (near real-time), 0.25° daily",
    independence="verified",
)
