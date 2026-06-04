/**
 * PulseLayer.tsx — Custom MapLibre WebGL layer for animated event pulses.
 *
 * Implements MapLibre's CustomLayerInterface. Each EventPulse is rendered as
 * a screen-space circle via WebGL with:
 *   - Color from CATEGORY_COLORS[event.category[0]]
 *   - Radius from computePulseState().radius
 *   - Opacity from computePulseState().opacity
 *   - Animation oscillation period from computePulseState().period_ms
 *
 * Events filtered out by activeFilters are skipped during vertex upload.
 * Clicking on a pulse fires onPulseClick with the EventPulse.
 *
 * Shader strings are stable constants — tested via snapshot in PulseLayer.test.tsx.
 *
 * PLAN-F-019 TASK-006
 */

import React, { useEffect, useRef, useCallback } from 'react';
import type { EventPulse } from '../types/map.types';
import { getCategoryColor } from '../lib/color-palette';
import { computePulseState, MIN_OPACITY } from '../lib/pulse-animation';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface MapFilters {
  categories: string[];
  intensities: number[];
}

export interface PulseLayerProps {
  /** MapLibre Map instance */
  map: unknown;
  events: EventPulse[];
  activeFilters: MapFilters;
  onPulseClick?: (event: EventPulse) => void;
}

// ── Shader source strings ─────────────────────────────────────────────────────
// Exported so snapshot tests can guard against accidental regression.

export const VERTEX_SHADER_SOURCE = `
  precision highp float;
  attribute vec2 a_pos;
  attribute float a_radius;
  attribute vec4 a_color;
  attribute float a_opacity;

  uniform mat4 u_matrix;
  varying vec4 v_color;
  varying float v_opacity;

  void main() {
    gl_Position = u_matrix * vec4(a_pos, 0.0, 1.0);
    gl_PointSize = a_radius * 2.0;
    v_color = a_color;
    v_opacity = a_opacity;
  }
`.trim();

export const FRAGMENT_SHADER_SOURCE = `
  precision mediump float;
  varying vec4 v_color;
  varying float v_opacity;

  void main() {
    // Soft circular gradient using smoothstep on distance from center.
    vec2 coord = gl_PointCoord - vec2(0.5);
    float dist = length(coord);
    float alpha = smoothstep(0.5, 0.3, dist) * v_opacity;
    if (alpha < 0.01) discard;
    gl_FragColor = vec4(v_color.rgb, alpha);
  }
`.trim();

// ── Hex color to normalized RGB ───────────────────────────────────────────────

function hexToRgb(hex: string): [number, number, number] {
  const c = hex.replace('#', '');
  const r = parseInt(c.slice(0, 2), 16) / 255;
  const g = parseInt(c.slice(2, 4), 16) / 255;
  const b = parseInt(c.slice(4, 6), 16) / 255;
  return [r, g, b];
}

// ── Filter helper (exported for unit tests) ───────────────────────────────────

/**
 * Returns only the events that pass the current filter criteria.
 */
export function applyFilters(
  events: EventPulse[],
  filters: MapFilters,
): EventPulse[] {
  return events.filter((e) => {
    const categoryMatch = e.category.some((c) => filters.categories.includes(c));
    const intensityMatch = filters.intensities.includes(e.intensity);
    return categoryMatch && intensityMatch;
  });
}

// ── WebGL context types ───────────────────────────────────────────────────────

interface GL {
  createShader: (type: number) => WebGLShader | null;
  shaderSource: (shader: WebGLShader, source: string) => void;
  compileShader: (shader: WebGLShader) => void;
  createProgram: () => WebGLProgram | null;
  attachShader: (program: WebGLProgram, shader: WebGLShader) => void;
  linkProgram: (program: WebGLProgram) => void;
  useProgram: (program: WebGLProgram | null) => void;
  createBuffer: () => WebGLBuffer | null;
  bindBuffer: (target: number, buffer: WebGLBuffer | null) => void;
  bufferData: (target: number, data: Float32Array, usage: number) => void;
  enableVertexAttribArray: (index: number) => void;
  vertexAttribPointer: (index: number, size: number, type: number, normalized: boolean, stride: number, offset: number) => void;
  getAttribLocation: (program: WebGLProgram, name: string) => number;
  getUniformLocation: (program: WebGLProgram, name: string) => WebGLUniformLocation | null;
  uniformMatrix4fv: (location: WebGLUniformLocation | null, transpose: boolean, value: Float32List) => void;
  drawArrays: (mode: number, first: number, count: number) => void;
  deleteBuffer: (buffer: WebGLBuffer | null) => void;
  deleteProgram: (program: WebGLProgram | null) => void;
  VERTEX_SHADER: number;
  FRAGMENT_SHADER: number;
  ARRAY_BUFFER: number;
  STATIC_DRAW: number;
  FLOAT: number;
  POINTS: number;
}

// ── Component ─────────────────────────────────────────────────────────────────

const LAYER_ID = 'intelligence-map-pulse-layer';

export const PulseLayer: React.FC<PulseLayerProps> = ({
  map,
  events,
  activeFilters,
  onPulseClick,
}) => {
  const glRef = useRef<GL | null>(null);
  const programRef = useRef<WebGLProgram | null>(null);
  const bufferRef = useRef<WebGLBuffer | null>(null);
  const rafRef = useRef<number | null>(null);
  const eventsRef = useRef<EventPulse[]>(events);
  const filtersRef = useRef<MapFilters>(activeFilters);

  eventsRef.current = events;
  filtersRef.current = activeFilters;

  const compileShader = useCallback(
    (gl: GL, type: number, source: string): WebGLShader | null => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      return shader;
    },
    [],
  );

  const buildVertexData = useCallback(
    (filteredEvents: EventPulse[], now: Date, projMatrix: Float32Array | number[]): Float32Array => {
      // Each vertex: [x_ndc, y_ndc, radius, r, g, b, opacity] = 7 floats
      const STRIDE = 7;
      const data = new Float32Array(filteredEvents.length * STRIDE);
      filteredEvents.forEach((e, i) => {
        const state = computePulseState(
          {
            timestamp: e.timestamp,
            relevance_window_end: e.relevance_window_end,
            intensity: e.intensity,
          },
          now,
        );
        const colorHex = getCategoryColor(e.category[0] ?? '');
        const [r, g, b] = hexToRgb(colorHex);
        const opacity = state.period_ms === 0 ? MIN_OPACITY : state.opacity;
        // Position is in lon/lat; MapLibre projection matrix converts to clip space.
        // For the GPU buffer we store raw lon/lat and rely on u_matrix.
        data[i * STRIDE + 0] = e.lon;
        data[i * STRIDE + 1] = e.lat;
        data[i * STRIDE + 2] = state.radius;
        data[i * STRIDE + 3] = r;
        data[i * STRIDE + 4] = g;
        data[i * STRIDE + 5] = b;
        data[i * STRIDE + 6] = opacity;
      });
      return data;
    },
    [],
  );

  useEffect(() => {
    const m = map as {
      addLayer: (layer: unknown) => void;
      removeLayer: (id: string) => void;
      getLayer: (id: string) => unknown;
      on: (event: string, layer: string, cb: (e: unknown) => void) => void;
      off: (event: string, layer: string, cb: (e: unknown) => void) => void;
      queryRenderedFeatures?: (point: unknown, opts: unknown) => unknown[];
    } | null;
    if (!m) return;

    const customLayer = {
      id: LAYER_ID,
      type: 'custom' as const,
      renderingMode: '2d' as const,

      onAdd(_mapInstance: unknown, gl: GL) {
        glRef.current = gl;

        const vertShader = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER_SOURCE);
        const fragShader = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER_SOURCE);

        const program = gl.createProgram();
        if (program && vertShader && fragShader) {
          gl.attachShader(program, vertShader);
          gl.attachShader(program, fragShader);
          gl.linkProgram(program);
          programRef.current = program;
        }

        bufferRef.current = gl.createBuffer();
      },

      render(matrix: number[]) {
        const gl = glRef.current;
        const program = programRef.current;
        const buffer = bufferRef.current;
        if (!gl || !program || !buffer) return;

        const filteredEvents = applyFilters(eventsRef.current, filtersRef.current);
        if (filteredEvents.length === 0) return;

        const now = new Date();
        const vertexData = buildVertexData(filteredEvents, now, matrix);

        gl.useProgram(program);
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, vertexData, gl.STATIC_DRAW);

        const STRIDE = 7 * 4; // 7 floats × 4 bytes
        const posLoc = gl.getAttribLocation(program, 'a_pos');
        const radLoc = gl.getAttribLocation(program, 'a_radius');
        const colLoc = gl.getAttribLocation(program, 'a_color');
        const opLoc = gl.getAttribLocation(program, 'a_opacity');
        const matLoc = gl.getUniformLocation(program, 'u_matrix');

        gl.enableVertexAttribArray(posLoc);
        gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, STRIDE, 0);
        gl.enableVertexAttribArray(radLoc);
        gl.vertexAttribPointer(radLoc, 1, gl.FLOAT, false, STRIDE, 2 * 4);
        gl.enableVertexAttribArray(colLoc);
        gl.vertexAttribPointer(colLoc, 3, gl.FLOAT, false, STRIDE, 3 * 4);
        gl.enableVertexAttribArray(opLoc);
        gl.vertexAttribPointer(opLoc, 1, gl.FLOAT, false, STRIDE, 6 * 4);

        gl.uniformMatrix4fv(matLoc, false, matrix);
        gl.drawArrays(gl.POINTS, 0, filteredEvents.length);
      },

      onRemove() {
        const gl = glRef.current;
        if (gl) {
          if (bufferRef.current) gl.deleteBuffer(bufferRef.current);
          if (programRef.current) gl.deleteProgram(programRef.current);
        }
        if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      },
    };

    m.addLayer(customLayer);

    const handleClick = (e: unknown) => {
      const evt = e as { point?: { x: number; y: number }; lngLat?: { lng: number; lat: number } };
      if (!evt.lngLat || !onPulseClick) return;
      // Find the closest event to the click point.
      const filtered = applyFilters(eventsRef.current, filtersRef.current);
      const closest = filtered.reduce<EventPulse | null>((best, ev) => {
        const dist = Math.hypot(ev.lon - evt.lngLat!.lng, ev.lat - evt.lngLat!.lat);
        if (!best) return ev;
        const bestDist = Math.hypot(best.lon - evt.lngLat!.lng, best.lat - evt.lngLat!.lat);
        return dist < bestDist ? ev : best;
      }, null);
      if (closest && Math.hypot(closest.lon - evt.lngLat.lng, closest.lat - evt.lngLat.lat) < 0.5) {
        onPulseClick(closest);
      }
    };

    m.on('click', LAYER_ID, handleClick);

    return () => {
      m.off('click', LAYER_ID, handleClick);
      if (m.getLayer(LAYER_ID)) m.removeLayer(LAYER_ID);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, compileShader, buildVertexData]);

  // No DOM output — rendering is entirely via MapLibre WebGL.
  return null;
};

export default PulseLayer;
