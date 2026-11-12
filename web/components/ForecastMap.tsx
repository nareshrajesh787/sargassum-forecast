"use client";
import { useEffect, useRef } from "react";
import type { Map as MLMap, GeoJSONSource } from "maplibre-gl";
import type { SiteForecast } from "@/lib/types";
import { probColor } from "@/lib/colors";

type Props = {
  sites: SiteForecast[];
  lead: number;
  selected: string | null;
  onSelect: (id: string) => void;
  drift: GeoJSON.FeatureCollection | null;
  showDrift: boolean;
};

const OSM_STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors",
      maxzoom: 19,
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};

function siteFeatures(sites: SiteForecast[], lead: number, selected: string | null): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: sites.map((s) => {
      const l = s.leads.find((x) => x.lead_days === lead);
      const p = l?.probability ?? 0;
      return {
        type: "Feature",
        geometry: { type: "Point", coordinates: [s.lon, s.lat] },
        properties: { id: s.id, name: s.name, p, hi: l?.interval_80[1] ?? p, color: probColor(p), hiColor: probColor(l?.interval_80[1] ?? p), sel: s.id === selected ? 1 : 0 },
      };
    }),
  };
}

export default function ForecastMap({ sites, lead, selected, onSelect, drift, showDrift }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const ready = useRef(false);
  const applyRef = useRef<() => void>(() => {});
  // always applies the latest props; called on map load and whenever props change
  applyRef.current = () => {
    const m = map.current;
    if (!m || !ready.current) return;
    (m.getSource("sites") as GeoJSONSource | undefined)?.setData(siteFeatures(sites, lead, selected));
    const d: GeoJSON.FeatureCollection = showDrift && drift ? { type: "FeatureCollection", features: drift.features.filter((f) => f.properties?.lead === lead) } : { type: "FeatureCollection", features: [] };
    (m.getSource("drift") as GeoJSONSource | undefined)?.setData(d);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ml = (await import("maplibre-gl")).default;
      if (cancelled || !box.current) return;
      const m = new ml.Map({ container: box.current, style: OSM_STYLE, center: [-79.85, 26.15], zoom: 8.6, attributionControl: { compact: true } });
      m.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
      map.current = m;
      m.on("load", () => {
        m.addSource("drift", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        m.addLayer({ id: "drift", type: "circle", source: "drift", paint: { "circle-radius": 2, "circle-color": "#6250d6", "circle-opacity": 0.55 } });
        m.addSource("sites", { type: "geojson", data: siteFeatures(sites, lead, selected) });
        // uncertainty band: outer ring = upper end of the 80% interval, inner disc = served probability
        m.addLayer({ id: "sites-band", type: "circle", source: "sites", paint: { "circle-radius": 15, "circle-color": ["get", "hiColor"], "circle-opacity": 0.45 } });
        m.addLayer({ id: "sites", type: "circle", source: "sites", paint: { "circle-radius": 9, "circle-color": ["get", "color"], "circle-stroke-width": ["case", ["==", ["get", "sel"], 1], 3, 1.5], "circle-stroke-color": ["case", ["==", ["get", "sel"], 1], "#0b0b0b", "#ffffff"] } });
        m.on("click", "sites", (e) => { const id = e.features?.[0]?.properties?.id; if (id) onSelect(String(id)); });
        m.on("mouseenter", "sites", () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", "sites", () => (m.getCanvas().style.cursor = ""));
        ready.current = true;
        applyRef.current();
      });
    })();
    return () => { cancelled = true; map.current?.remove(); map.current = null; ready.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    applyRef.current();
  }, [sites, lead, selected, drift, showDrift]);

  return <div ref={box} className="map" role="img" aria-label="Map of the 8 Broward beaches coloured by forecast probability. Use the site list for keyboard access." />;
}
