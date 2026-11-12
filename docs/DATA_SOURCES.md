# Data sources

Updated in Phase 1 (details and measured coverage in `docs/FEASIBILITY.md`); finalised in Phase 7.
Every source keeps its own terms; code is MIT.

| Source | What we use | Terms / credit | Stored in repo? |
| --- | --- | --- | --- |
| FIU Sargassum Watch (Epicollect5), `sargassum-watch` export API | Beach reports → derived site-day severity labels | No explicit licence. FIU asks users of its Epicollect data to email Dr. Lowell Iporac. Courtesy email sent by the owner; **owner confirmed on 2026-11-12 that FIU agreed** (use of the data and publication of derived daily labels). Credit FIU Marine Macroalgae Research Lab. | Raw reports and photos: never committed or republished. Only a weekly summary row (`archive/fiu/manifest.csv`) plus derived labels where results need them (e.g. the observed severity class in `outputs/failure_gallery.csv`). |
| NOAA AOML / USF AFAI (ERDDAP `noaa_aoml_atlantic_oceanwatch_AFAI_1D`, `_3D`) | Satellite floating-algae index | ERDDAP licence attribute: "The data may be used and redistributed for free but is not intended for legal use, since it may contain inaccuracies…" (full text in `outputs/spike/s01_afai_metadata.json`). Credit NOAA AOML Atlantic OceanWatch and USF Optical Oceanography Lab (Hu et al. 2015). | No (cached under `data/raw/afai`). |
| NOAA/USF SIR v1.5 (`cwcgom.aoml.noaa.gov/SIR/`) | Outside benchmark; daily archive | Experimental product; NOAA/USF credit required. CC0 not confirmed. | Manifest committed (`archive/sir/manifest.csv`); file bytes as monthly GitHub prereleases `sir-archive-YYYY-MM`. |
| Copernicus Marine `GLOBAL_ANALYSISFORECAST_PHY_001_024` (SMOC `cmems_mod_glo_phy_anfc_merged-uv_PT1H-i`); `GLOBAL_MULTIYEAR_PHY_001_030`; `GLOBAL_MULTIYEAR_WAV_001_032` | Gridded currents and Stokes drift for drift | Copernicus Marine Service licence (attribution: "E.U. Copernicus Marine Service Information"). Needs a free account; credentials only in env / GitHub secrets. | No. |
| Open-Meteo Marine, Historical Forecast and Previous Runs APIs (models `meteofrance_currents`, `meteofrance_wave`, `gfs_seamless`) | Point currents, waves, SST, winds | CC BY 4.0; non-commercial; < 10,000 calls/day. Credit Open-Meteo.com, Météo-France, NOAA NCEP. | No (cached under `data/raw/openmeteo`). |
| NOAA CO-OPS | Tide predictions | Public domain. | No. |
| Natural Earth 10 m land | Coastline for distance-to-coast bands | Public domain. | No (downloaded to `data/raw/naturalearth`). |
| Copernicus Marine `WIND_GLO_PHY_L4_MY_012_006` / `_NRT_012_004` (hourly 0.125° L4 winds) | Gridded 10 m wind for P1 drift (windage) | Copernicus Marine Service licence (attribution). Same account as SMOC. | No. |
| OpenDrift (MET Norway) with roaring-landmask (GSHHG) | Lagrangian drift engine and coastline for stranding | GPL-2.0 (OpenDrift) — used as a library, not redistributed; GSHHG LGPL. Cite Dagestad et al. 2018. | No. |
