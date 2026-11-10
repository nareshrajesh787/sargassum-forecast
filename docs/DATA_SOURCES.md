# Data sources

Stub — filled in during Phase 1 (`docs/FEASIBILITY.md`) and finalised in Phase 7.
Every source keeps its own terms; code is MIT.

| Source | What we use | Terms / credit | Stored in repo? |
| --- | --- | --- | --- |
| FIU Sargassum Watch (Epicollect5), `sargassum-watch` export API | Beach reports → derived site-day severity labels | No explicit licence. FIU asks users of its Epicollect data to email Dr. Lowell Iporac. Courtesy email sent by owner: **status not recorded here yet**. Credit FIU Marine Macroalgae Research Lab. | No. Raw reports and photos are never committed or republished; only a weekly summary row (`archive/fiu/manifest.csv`). Derived daily labels published only if FIU agrees. |
| NOAA AOML / USF AFAI (ERDDAP `noaa_aoml_atlantic_oceanwatch_AFAI_1D`, `_3D`) | Satellite floating-algae index | "May be used and redistributed for free but is not intended for legal use." Credit NOAA AOML and USF Optical Oceanography Lab. | No (cached under `data/`). |
| NOAA/USF SIR v1.5 (`cwcgom.aoml.noaa.gov/SIR/`) | Outside benchmark; daily archive | Experimental product; NOAA/USF credit required. CC0 not confirmed. | Manifest committed (`archive/sir/manifest.csv`); file bytes as monthly GitHub prereleases `sir-archive-YYYY-MM`. |
| Copernicus Marine `GLOBAL_ANALYSISFORECAST_PHY_001_024` | Gridded currents for drift | Copernicus Marine licence (attribution). Needs a free account. | No. |
| Open-Meteo Marine + Historical Forecast APIs | Point currents, waves, winds | CC BY 4.0; non-commercial; < 10,000 calls/day. | No. |
| NOAA CO-OPS | Tide predictions | Public domain. | No. |
