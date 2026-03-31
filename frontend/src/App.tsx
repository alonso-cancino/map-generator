import { useEffect, useState } from "react";
import { loadBundle } from "./bundle";
import MapView from "./MapView";
import type { FrontendBundle } from "./types";

const bundlePath = import.meta.env.VITE_MAP_BUNDLE_PATH ?? `${import.meta.env.BASE_URL}map_bundle.json`;

export default function App() {
  const [bundle, setBundle] = useState<FrontendBundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    loadBundle(bundlePath)
      .then((loadedBundle) => {
        if (!cancelled) {
          setBundle(loadedBundle);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load map bundle.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="app-shell">
      {error !== null ? <section className="status-card error">{error}</section> : null}
      {error === null && bundle === null ? (
        <section className="status-card">Loading bundle from {bundlePath}</section>
      ) : null}
      {bundle !== null ? <MapView bundle={bundle} /> : null}
    </main>
  );
}
