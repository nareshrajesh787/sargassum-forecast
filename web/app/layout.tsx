import type { Metadata, Viewport } from "next";
import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "Broward sargassum forecast",
  description: "Experimental beach-level sargassum forecast for 8 Broward County, FL beaches, scored against FIU Sargassum Watch reports.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <Nav />
        <main id="main">{children}</main>
        <footer>
          <p>
            Experimental research forecast, not a warning system. Beach observations: FIU Sargassum Watch (Marine
            Macroalgae Research Lab). Satellite AFAI: NOAA AOML Atlantic OceanWatch and USF Optical Oceanography Lab.
            Currents: E.U. Copernicus Marine Service Information. Winds and waves: Open-Meteo.com (Météo-France, NOAA
            GFS). Tides: NOAA CO-OPS. Map data © OpenStreetMap contributors.
          </p>
          <p>
            Code (MIT): <a href="https://github.com/nareshrajesh787/sargassum-forecast">github.com/nareshrajesh787/sargassum-forecast</a>.
            Contact: nareshrajesh787@gmail.com
          </p>
        </footer>
      </body>
    </html>
  );
}
