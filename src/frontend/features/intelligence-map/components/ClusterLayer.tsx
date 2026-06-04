/**
 * ClusterLayer.tsx — Renders Supercluster cluster bubbles on the MapLibre map.
 *
 * Adds a GeoJSON source and circle layer to the map for cluster features.
 * Clicking a cluster calls onClusterClick which the parent uses to flyTo zoom+1.
 * Hovering a cluster shows a <ClusterDonut> tooltip.
 *
 * PLAN-F-019 TASK-005
 */

import React, { useEffect, useRef, useState } from 'react';
import type { ClusterProps } from '../types/map.types';
import { CATEGORY_COLORS, getCategoryColor } from '../lib/color-palette';
import { extractCategoriesFromCluster } from '../lib/cluster-properties';
import ClusterDonut from './ClusterDonut';

// ── Types ─────────────────────────────────────────────────────────────────────

interface GeoJSONFeature {
  type: 'Feature';
  geometry: { type: string; coordinates: [number, number] };
  properties: Record<string, unknown> | null;
}

interface FeatureCollection {
  type: 'FeatureCollection';
  features: GeoJSONFeature[];
}

export interface ClusterLayerProps {
  /** MapLibre Map instance */
  map: unknown;
  clusters: FeatureCollection;
  onClusterClick?: (cluster: GeoJSONFeature) => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Returns the category with the highest count from the cluster properties.
 * Exported for direct unit testing.
 */
export function getDominantCategory(
  categories: Record<string, number>,
): string | null {
  const entries = Object.entries(categories);
  if (entries.length === 0) return null;
  return entries.reduce((best, curr) =>
    curr[1] > best[1] ? curr : best,
  )[0];
}

function intensityToColor(maxIntensity: number): string {
  if (maxIntensity >= 5) return '#D55E00'; // vermillion — critical
  if (maxIntensity === 4) return '#E69F00'; // orange — high
  if (maxIntensity === 3) return '#F0E442'; // yellow — medium
  if (maxIntensity === 2) return '#56B4E9'; // sky blue — low
  return '#BBBBBB'; // grey — minimal
}

function eventCountToRadius(count: number): number {
  return Math.max(12, Math.log2(count + 1) * 10);
}

// ── Component ─────────────────────────────────────────────────────────────────

export const ClusterLayer: React.FC<ClusterLayerProps> = ({
  map,
  clusters,
  onClusterClick,
}) => {
  const [hoveredCluster, setHoveredCluster] = useState<GeoJSONFeature | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);
  const mapRef = useRef<unknown>(map);
  mapRef.current = map;

  const SOURCE_ID = 'intelligence-map-clusters';
  const LAYER_ID = 'intelligence-map-cluster-circles';

  useEffect(() => {
    const m = mapRef.current as {
      getSource: (id: string) => unknown;
      addSource: (id: string, spec: unknown) => void;
      addLayer: (spec: unknown) => void;
      on: (event: string, layer: string, cb: (e: unknown) => void) => void;
      off: (event: string, layer: string, cb: (e: unknown) => void) => void;
      removeLayer: (id: string) => void;
      removeSource: (id: string) => void;
      getLayer: (id: string) => unknown;
    } | null;
    if (!m) return;

    // Add source
    if (!m.getSource(SOURCE_ID)) {
      m.addSource(SOURCE_ID, {
        type: 'geojson',
        data: clusters,
      });
    }

    // Add circle layer
    if (!m.getLayer(LAYER_ID)) {
      m.addLayer({
        id: LAYER_ID,
        type: 'circle',
        source: SOURCE_ID,
        paint: {
          'circle-color': '#0072B2',
          'circle-radius': 14,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#FFFFFF',
        },
      });
    }

    const handleClick = (e: unknown) => {
      const evt = e as { features?: GeoJSONFeature[]; originalEvent?: MouseEvent };
      if (evt.features && evt.features.length > 0 && onClusterClick) {
        onClusterClick(evt.features[0]);
      }
    };

    const handleMouseEnter = (e: unknown) => {
      const evt = e as { features?: GeoJSONFeature[]; point?: { x: number; y: number } };
      if (evt.features && evt.features.length > 0) {
        setHoveredCluster(evt.features[0]);
        if (evt.point) setTooltipPos(evt.point);
      }
    };

    const handleMouseLeave = () => {
      setHoveredCluster(null);
      setTooltipPos(null);
    };

    m.on('click', LAYER_ID, handleClick);
    m.on('mouseenter', LAYER_ID, handleMouseEnter);
    m.on('mouseleave', LAYER_ID, handleMouseLeave);

    return () => {
      m.off('click', LAYER_ID, handleClick);
      m.off('mouseenter', LAYER_ID, handleMouseEnter);
      m.off('mouseleave', LAYER_ID, handleMouseLeave);
      if (m.getLayer(LAYER_ID)) m.removeLayer(LAYER_ID);
      if (m.getSource(SOURCE_ID)) m.removeSource(SOURCE_ID);
    };
  }, [map, clusters, onClusterClick]);

  // Update source data when clusters change.
  useEffect(() => {
    const m = mapRef.current as {
      getSource: (id: string) => { setData: (d: unknown) => void } | undefined;
    } | null;
    if (!m) return;
    const src = m.getSource(SOURCE_ID) as { setData?: (d: unknown) => void } | undefined;
    src?.setData?.(clusters);
  }, [clusters]);

  const hoveredCategories =
    hoveredCluster?.properties
      ? extractCategoriesFromCluster(hoveredCluster.properties)
      : null;

  return (
    <>
      {hoveredCluster && hoveredCategories && tooltipPos && (
        <div
          style={{
            position: 'absolute',
            left: tooltipPos.x + 10,
            top: tooltipPos.y - 50,
            pointerEvents: 'none',
            zIndex: 1000,
          }}
          data-testid="cluster-donut-tooltip"
        >
          <ClusterDonut
            categories={hoveredCategories}
            colors={CATEGORY_COLORS}
          />
        </div>
      )}
    </>
  );
};

// Re-export helpers for external unit tests.
export { intensityToColor, eventCountToRadius, getCategoryColor };

export default ClusterLayer;
