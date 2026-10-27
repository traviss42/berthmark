import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Plus,
  Minus,
  RotateCcw,
  X,
  Compass,
  Navigation,
  Anchor,
  Ship,
  Waves,
  Wind,
  Globe,
  TrendingUp,
  TrendingDown,
  Minus as MinusIcon,
  AlertTriangle,
  Check,
  Crosshair,
} from 'lucide-react';
import type { Port, RiskAssessment, VesselClass, AlternativePortRecommendation } from '@/types';
import {
  formatVesselClass,
  formatQueueVariance,
  TIER_COLORS,
  TIER_LABELS,
} from '@/utils/riskDisplay';
import { AlternativePortDiversion } from './AlternativePortDiversion';
import { WORLD_MAP_PATH } from './worldMapData';

export interface InteractiveMapProps {
  ports: Port[];
  assessments: Map<string, RiskAssessment>;
  vesselClass: VesselClass;
  onSelectPort?: (portId: string) => void;
  onAddFirstPort?: () => void;
  onAddPort?: (port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>) => Promise<any> | void;
  className?: string;
}

// SVG Map dimensions and zoom bounds
const MAP_WIDTH = 1000;
const MAP_HEIGHT = 500;
const MIN_ZOOM = 1;
const MAX_ZOOM = 24;

function projectCoordinates(lat: number, lon: number): { x: number; y: number } {
  // Equirectangular projection
  const clampedLat = Math.max(-85, Math.min(85, lat));
  const clampedLon = Math.max(-180, Math.min(180, lon));
  const x = ((clampedLon + 180) / 360) * MAP_WIDTH;
  const y = ((90 - clampedLat) / 180) * MAP_HEIGHT;
  return { x, y };
}

export const InteractiveMap: React.FC<InteractiveMapProps> = ({
  ports,
  assessments,
  vesselClass,
  onSelectPort,
  onAddFirstPort,
  onAddPort,
  className = '',
}) => {
  const [selectedPortId, setSelectedPortId] = useState<string | null>(null);
  const [selectedAlternative, setSelectedAlternative] = useState<{
    alternative: AlternativePortRecommendation;
    primaryPort: Port;
  } | null>(null);
  const [addedAltLocode, setAddedAltLocode] = useState<string | null>(null);
  const [addingAlt, setAddingAlt] = useState(false);
  const [zoom, setZoom] = useState<number>(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [startPan, setStartPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const mapContainerRef = useRef<HTMLDivElement>(null);

  // Filter ports matching the selected vesselClass
  const visiblePorts = useMemo(() => {
    return ports.filter((port) => {
      // If port has an explicit watched vesselClass, only show when selected vesselClass matches
      if (port.vesselClass) {
        return port.vesselClass === vesselClass;
      }
      // If assessment has vesselClass, only show when it matches
      const assessment = assessments.get(port.id);
      if (assessment?.vesselClass) {
        return assessment.vesselClass === vesselClass;
      }
      return true;
    });
  }, [ports, assessments, vesselClass]);

  // Recenter / Reset map view to show full global Earth
  const recenter = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setSelectedPortId(null);
    setSelectedAlternative(null);
  }, []);

  // Handle Escape key to close popups
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedPortId(null);
        setSelectedAlternative(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Center and zoom map to specified coordinates with viewport boundary clamping
  const zoomToCoords = useCallback((lat: number, lon: number, targetZoom = 8) => {
    const { x, y } = projectCoordinates(lat, lon);
    const newZoom = Math.min(Math.max(targetZoom, MIN_ZOOM), MAX_ZOOM);
    const rawPanX = MAP_WIDTH / 2 - x * newZoom;
    const rawPanY = MAP_HEIGHT / 2 - y * newZoom;

    const minPanX = MAP_WIDTH * (1 - newZoom);
    const minPanY = MAP_HEIGHT * (1 - newZoom);

    setZoom(newZoom);
    setPan({
      x: Math.min(0, Math.max(minPanX, rawPanX)),
      y: Math.min(0, Math.max(minPanY, rawPanY)),
    });
  }, []);

  // Zoom controls with viewport bounding and extended range
  const handleZoomIn = () => setZoom((z) => Math.min(Number((z * 1.5).toFixed(2)), MAX_ZOOM));
  const handleZoomOut = () =>
    setZoom((z) => {
      const next = Math.max(Number((z / 1.5).toFixed(2)), MIN_ZOOM);
      if (next === 1) {
        setPan({ x: 0, y: 0 });
      }
      return next;
    });

  // Wheel zoom centered on mouse cursor position
  const handleWheel = (e: React.WheelEvent) => {
    if ((e.target as HTMLElement).closest('[data-testid="map-popup"], [data-testid="map-alt-popup"]')) {
      return;
    }
    e.preventDefault();
    const rect = mapContainerRef.current?.getBoundingClientRect();
    if (!rect) return;

    const cursorX = ((e.clientX - rect.left) / rect.width) * MAP_WIDTH;
    const cursorY = ((e.clientY - rect.top) / rect.height) * MAP_HEIGHT;

    const zoomFactor = e.deltaY < 0 ? 1.25 : 0.8;
    const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number((zoom * zoomFactor).toFixed(2))));

    if (nextZoom === zoom) return;

    if (nextZoom === MIN_ZOOM) {
      setZoom(MIN_ZOOM);
      setPan({ x: 0, y: 0 });
      return;
    }

    const scaleRatio = nextZoom / zoom;
    const rawPanX = cursorX - (cursorX - pan.x) * scaleRatio;
    const rawPanY = cursorY - (cursorY - pan.y) * scaleRatio;

    const minPanX = MAP_WIDTH * (1 - nextZoom);
    const minPanY = MAP_HEIGHT * (1 - nextZoom);

    setZoom(nextZoom);
    setPan({
      x: Math.min(0, Math.max(minPanX, rawPanX)),
      y: Math.min(0, Math.max(minPanY, rawPanY)),
    });
  };

  // Pan handlers with strict boundary clamping to keep Earth fully inside viewport
  const handleMouseDown = (e: React.MouseEvent) => {
    // Only pan if clicking map backdrop, not interactive pins/popups
    if (
      (e.target as HTMLElement).closest(
        '[data-testid^="map-pin-"], [data-testid^="map-alt-pin-"], [data-testid="map-popup"], [data-testid="map-alt-popup"]'
      )
    ) {
      return;
    }
    setIsPanning(true);
    setStartPan({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isPanning) return;
    const rawX = e.clientX - startPan.x;
    const rawY = e.clientY - startPan.y;

    // Strict clamping so Earth is never thrown out of the viewport
    const minPanX = Math.min(0, MAP_WIDTH * (1 - zoom));
    const minPanY = Math.min(0, MAP_HEIGHT * (1 - zoom));

    setPan({
      x: Math.min(0, Math.max(minPanX, rawX)),
      y: Math.min(0, Math.max(minPanY, rawY)),
    });
  };

  const handleMouseUp = () => setIsPanning(false);

  // Selected port & assessment
  const selectedPort = useMemo(
    () => visiblePorts.find((p) => p.id === selectedPortId) ?? null,
    [visiblePorts, selectedPortId]
  );
  const selectedAssessment = useMemo(
    () => (selectedPortId ? assessments.get(selectedPortId) ?? null : null),
    [assessments, selectedPortId]
  );

  // Memoize diversion routes and safe haven alternative pins strictly from dynamic API coordinates
  const { diversionRoutes, alternativePins } = useMemo(() => {
    interface RouteItem {
      id: string;
      primaryPort: Port;
      alternative: AlternativePortRecommendation;
      startX: number;
      startY: number;
      endX: number;
      endY: number;
      distanceNm: number;
    }
    interface PinItem {
      alternative: AlternativePortRecommendation;
      primaryPort: Port;
      x: number;
      y: number;
    }

    const routes: RouteItem[] = [];
    const pinsMap = new Map<string, PinItem>();

    // If a port is selected, focus on its alternatives. If no port is selected, show for visible high-risk ports.
    const targetPorts = selectedPort
      ? [selectedPort]
      : visiblePorts.filter((p) => assessments.get(p.id)?.compositeTier === 'high');

    for (const port of targetPorts) {
      const assessment = assessments.get(port.id);
      if (!assessment || assessment.compositeTier !== 'high' || !assessment.alternatives) {
        continue;
      }
      const viableAlts = assessment.alternatives
        .filter((a) => a.riskTier !== 'high')
        .sort((a, b) => a.distanceNm - b.distanceNm)
        .slice(0, 3);

      const start = projectCoordinates(port.lat, port.lon);

      for (const alt of viableAlts) {
        if (
          typeof alt.lat !== 'number' ||
          typeof alt.lon !== 'number' ||
          isNaN(alt.lat) ||
          isNaN(alt.lon)
        ) {
          continue;
        }
        const end = projectCoordinates(alt.lat, alt.lon);

        routes.push({
          id: `${port.id}-${alt.portId}`,
          primaryPort: port,
          alternative: alt,
          startX: start.x,
          startY: start.y,
          endX: end.x,
          endY: end.y,
          distanceNm: alt.distanceNm,
        });

        const pinKey = alt.portId || alt.unlocode;
        if (!pinsMap.has(pinKey)) {
          pinsMap.set(pinKey, {
            alternative: alt,
            primaryPort: port,
            x: end.x,
            y: end.y,
          });
        }
      }
    }

    return {
      diversionRoutes: routes,
      alternativePins: Array.from(pinsMap.values()),
    };
  }, [selectedPort, visiblePorts, assessments]);

  // Inverse zoom factor to keep pins and badges a constant, crisp size on screen
  const invZoom = 1 / zoom;

  return (
    <div
      ref={mapContainerRef}
      role="region"
      aria-label="Interactive Port Risk Map"
      data-testid="interactive-map-container"
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      className={`relative w-full h-[600px] bg-slate-900 rounded-2xl overflow-hidden border border-slate-800 shadow-lg select-none cursor-grab ${
        isPanning ? 'cursor-grabbing' : ''
      } ${className}`}
    >
      {/* ── World Basemap SVG ── */}
      <svg
        viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
        className="w-full h-full"
        onClick={() => {
          setSelectedPortId(null);
          setSelectedAlternative(null);
        }}
      >
        <defs>
          <radialGradient id="oceanGradient" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#0f172a" />
            <stop offset="100%" stopColor="#020617" />
          </radialGradient>
          <marker
            id="diversion-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#06b6d4" />
          </marker>
        </defs>

        {/* Ocean Background */}
        <rect width={MAP_WIDTH} height={MAP_HEIGHT} fill="url(#oceanGradient)" />

        <g
          transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}
          className="transition-transform duration-75 ease-out"
        >
          {/* Latitude & Longitude Graticule lines */}
          <g stroke="#1e293b" strokeWidth={0.75 * invZoom} strokeDasharray={`${3 * invZoom} ${3 * invZoom}`}>
            {/* Latitudes */}
            <line x1="0" y1="125" x2={MAP_WIDTH} y2="125" />
            <line x1="0" y1="250" x2={MAP_WIDTH} y2="250" />
            <line x1="0" y1="375" x2={MAP_WIDTH} y2="375" />
            {/* Longitudes */}
            <line x1="250" y1="0" x2="250" y2={MAP_HEIGHT} />
            <line x1="500" y1="0" x2="500" y2={MAP_HEIGHT} />
            <line x1="750" y1="0" x2="750" y2={MAP_HEIGHT} />
          </g>

          {/* Realistic High-Fidelity Global Coastlines (Natural Earth 110m) */}
          <path
            d={WORLD_MAP_PATH}
            fill="#1e293b"
            stroke="#334155"
            strokeWidth={Math.max(0.15, 0.6 * invZoom)}
            className="transition-colors"
          />

          {/* ── Diversion Route Vectors ── */}
          <g data-testid="map-diversion-routes">
            {diversionRoutes.map((route) => {
              const midX = (route.startX + route.endX) / 2;
              const midY = (route.startY + route.endY) / 2;
              return (
                <g
                  key={route.id}
                  data-testid={`map-diversion-route-${route.alternative.portId}`}
                  className="pointer-events-none"
                >
                  <line
                    data-testid={`map-diversion-line-${route.alternative.portId}`}
                    x1={route.startX}
                    y1={route.startY}
                    x2={route.endX}
                    y2={route.endY}
                    stroke="#06b6d4"
                    strokeWidth={2 * invZoom}
                    strokeDasharray={`${4 * invZoom} ${3 * invZoom}`}
                    markerEnd="url(#diversion-arrow)"
                    opacity="0.85"
                  />
                  {/* Midpoint Distance Badge */}
                  <g
                    data-testid={`map-diversion-badge-${route.alternative.portId}`}
                    transform={`translate(${midX}, ${midY}) scale(${invZoom})`}
                  >
                    <rect
                      x="-22"
                      y="-9"
                      width="44"
                      height="14"
                      rx="4"
                      fill="#083344"
                      stroke="#06b6d4"
                      strokeWidth="1"
                      opacity="0.9"
                    />
                    <text
                      y="1"
                      textAnchor="middle"
                      fill="#67e8f9"
                      fontSize="7.5"
                      fontWeight="bold"
                      className="font-mono"
                    >
                      {Math.round(route.distanceNm)} NM
                    </text>
                  </g>
                </g>
              );
            })}
          </g>

          {/* ── Recommended Alternative Safe Haven Pins ── */}
          <g data-testid="map-alternative-pins">
            {alternativePins.map((pin) => (
              <g
                key={pin.alternative.portId}
                data-testid={`map-alt-pin-${pin.alternative.portId}`}
                tabIndex={0}
                role="button"
                aria-label={`Safe Haven Alternative: ${pin.alternative.portName} (${pin.alternative.unlocode})`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedAlternative({
                    alternative: pin.alternative,
                    primaryPort: pin.primaryPort,
                  });
                  if (zoom < 6) {
                    zoomToCoords(
                      typeof pin.alternative.lat === 'number' ? pin.alternative.lat : pin.primaryPort.lat,
                      typeof pin.alternative.lon === 'number' ? pin.alternative.lon : pin.primaryPort.lon,
                      6
                    );
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSelectedAlternative({
                      alternative: pin.alternative,
                      primaryPort: pin.primaryPort,
                    });
                    if (zoom < 6) {
                      zoomToCoords(
                        typeof pin.alternative.lat === 'number' ? pin.alternative.lat : pin.primaryPort.lat,
                        typeof pin.alternative.lon === 'number' ? pin.alternative.lon : pin.primaryPort.lon,
                        6
                      );
                    }
                  }
                }}
                className="cursor-pointer focus:outline-none group"
                transform={`translate(${pin.x}, ${pin.y}) scale(${invZoom})`}
              >
                <title>{`Safe Haven: ${pin.alternative.portName} (${pin.alternative.unlocode}) - +${pin.alternative.depthMarginM.toFixed(1)}m margin`}</title>

                {/* Outer pulsing ring */}
                <circle
                  r="16"
                  fill="#06b6d4"
                  opacity="0.25"
                  className="animate-ping"
                />

                {/* Diamond Safe Haven Pin */}
                <polygon
                  points="0,-10 10,0 0,10 -10,0"
                  fill="#0891b2"
                  stroke="#e0f2fe"
                  strokeWidth="1.75"
                  className="transition-transform duration-200 group-hover:scale-125 drop-shadow-md"
                />
                <circle r="3" fill="#ffffff" />

                {/* Pin Port Code Label */}
                <text
                  y="-13"
                  textAnchor="middle"
                  fill="#a5f3fc"
                  fontSize="8.5"
                  fontWeight="bold"
                  className="pointer-events-none drop-shadow-md font-mono"
                >
                  {pin.alternative.unlocode}
                </text>
                <text
                  y="19"
                  textAnchor="middle"
                  fill="#34d399"
                  fontSize="7.5"
                  fontWeight="bold"
                  className="pointer-events-none drop-shadow-md font-mono"
                >
                  +{pin.alternative.depthMarginM.toFixed(1)}m
                </text>
              </g>
            ))}
          </g>

          {/* ── Monitored Primary Port Markers ── */}
          <g data-testid="map-primary-pins">
            {visiblePorts.map((port) => {
              const { x, y } = projectCoordinates(port.lat, port.lon);
              const assessment = assessments.get(port.id);
              const tier = assessment?.compositeTier ?? 'low';
              const isSelected = port.id === selectedPortId;

              // Pin styling per tier
              let pinColor = '#10B981'; // green / emerald
              if (tier === 'medium') pinColor = '#F59E0B'; // amber
              if (tier === 'high') pinColor = '#EF4444'; // red

              return (
                <g
                  key={port.id}
                  data-testid={`map-pin-${port.id}`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${port.name} - ${tier.toUpperCase()} Risk`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedPortId(port.id);
                    setSelectedAlternative(null);
                    if (onSelectPort) onSelectPort(port.id);
                    if (zoom < 6) {
                      zoomToCoords(port.lat, port.lon, 6);
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedPortId(port.id);
                      setSelectedAlternative(null);
                      if (zoom < 6) {
                        zoomToCoords(port.lat, port.lon, 6);
                      }
                    }
                  }}
                  className="cursor-pointer focus:outline-none group"
                  transform={`translate(${x}, ${y}) scale(${invZoom})`}
                >
                  {/* Micro tooltip / title */}
                  <title>{`${port.name} (${port.locode})`}</title>

                  {/* Pulsing selection aura */}
                  {isSelected && (
                    <circle
                      r="18"
                      fill={pinColor}
                      opacity="0.3"
                      className="animate-ping"
                    />
                  )}

                  {/* Outer Ring */}
                  <circle
                    r={isSelected ? '12' : '9'}
                    fill={pinColor}
                    stroke="#ffffff"
                    strokeWidth="2"
                    className="transition-all duration-200 group-hover:scale-125"
                  />

                  {/* Inner Center Dot */}
                  <circle r={isSelected ? '5' : '3.5'} fill="#ffffff" />

                  {/* Pin Port Code Label */}
                  <text
                    y="-14"
                    textAnchor="middle"
                    fill="#f8fafc"
                    fontSize="9"
                    fontWeight="bold"
                    className="pointer-events-none drop-shadow-md font-mono"
                  >
                    {port.locode}
                  </text>
                </g>
              );
            })}
          </g>
        </g>
      </svg>

      {/* ── Empty State Overlay ── */}
      {ports.length === 0 && (
        <div
          data-testid="map-empty-state"
          className="absolute inset-0 flex items-center justify-center bg-slate-900/80 backdrop-blur-xs p-6"
        >
          <div className="text-center max-w-sm p-6 bg-slate-800/90 border border-slate-700 rounded-2xl shadow-xl">
            <Globe className="w-12 h-12 text-slate-400 mx-auto mb-3" />
            <h3 className="text-base font-bold text-white mb-1">
              No Monitored Ports on Map
            </h3>
            <p className="text-xs text-slate-400 mb-5">
              Add ports to your watchlist to visualize global AIS congestion, depth clearances, and operational risks.
            </p>
            <button
              onClick={onAddFirstPort}
              data-testid="map-add-first-port"
              className="inline-flex items-center gap-2 px-4 py-2.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>+ Add First Port to Watchlist</span>
            </button>
          </div>
        </div>
      )}

      {/* ── Map Zoom & Recenter Controls ── */}
      <div className="absolute bottom-5 right-5 flex flex-col items-center gap-1.5 z-10">
        <div
          data-testid="map-zoom-level"
          className="px-2 py-0.5 text-[10px] font-mono font-bold text-center bg-slate-800/90 text-slate-300 rounded-md border border-slate-700 shadow-md backdrop-blur-xs select-none"
        >
          {zoom.toFixed(1)}x
        </div>
        <button
          onClick={handleZoomIn}
          aria-label="Zoom In"
          title="Zoom In"
          className="w-9 h-9 flex items-center justify-center bg-slate-800/90 hover:bg-slate-700 text-white rounded-lg border border-slate-700 shadow-md backdrop-blur-xs transition-colors cursor-pointer"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          onClick={handleZoomOut}
          aria-label="Zoom Out"
          title="Zoom Out"
          className="w-9 h-9 flex items-center justify-center bg-slate-800/90 hover:bg-slate-700 text-white rounded-lg border border-slate-700 shadow-md backdrop-blur-xs transition-colors cursor-pointer"
        >
          <Minus className="w-4 h-4" />
        </button>
        {selectedPort && (
          <button
            onClick={() => zoomToCoords(selectedPort.lat, selectedPort.lon, Math.max(zoom, 8))}
            aria-label="Focus Port"
            title="Focus on Selected Port & Alternatives"
            data-testid="map-focus-btn"
            className="w-9 h-9 flex items-center justify-center bg-blue-600 hover:bg-blue-500 text-white rounded-lg border border-blue-500 shadow-md backdrop-blur-xs transition-colors cursor-pointer"
          >
            <Crosshair className="w-4 h-4" />
          </button>
        )}
        <button
          onClick={recenter}
          aria-label="Reset View"
          title="Reset Map View"
          className="w-9 h-9 flex items-center justify-center bg-slate-800/90 hover:bg-slate-700 text-white rounded-lg border border-slate-700 shadow-md backdrop-blur-xs transition-colors cursor-pointer"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* ── Active Vessel Class Tag Overlay ── */}
      <div className="absolute top-4 left-4 bg-slate-800/90 border border-slate-700 text-slate-300 text-xs px-3 py-1.5 rounded-lg backdrop-blur-xs flex items-center gap-2 shadow-sm">
        <span className="w-2 h-2 rounded-full bg-blue-500" />
        <span>Evaluating for:</span>
        <span className="font-semibold text-white">
          {formatVesselClass(vesselClass)}
        </span>
        <span className="text-slate-400 text-[11px] font-mono">
          ({visiblePorts.length} of {ports.length} ports)
        </span>
      </div>

      {/* ── Filtered Out Advisory Banner ── */}
      {ports.length > 0 && visiblePorts.length === 0 && (
        <div
          data-testid="no-vessel-ports-alert"
          className="absolute top-14 left-4 z-10 flex items-center gap-2 px-3 py-2 bg-slate-800/90 border border-amber-500/40 text-xs text-amber-200 rounded-lg shadow-md backdrop-blur-xs"
        >
          <Ship className="w-4 h-4 text-amber-400 shrink-0" />
          <span>
            No ports watched for <strong>{formatVesselClass(vesselClass)}</strong> (all {ports.length} monitored ports belong to other vessel classes).
          </span>
        </div>
      )}

      {/* ── Direct On-Map Tooltip Popup (Drawer-Free) ── */}
      {selectedPort && (
        <div
          role="dialog"
          aria-modal="false"
          aria-label={`${selectedPort.name} Operational Details`}
          data-testid="map-popup"
          className="absolute top-4 right-4 z-20 w-84 sm:w-96 max-h-[560px] overflow-y-auto bg-white rounded-xl shadow-2xl border border-slate-200 p-4 animate-in fade-in zoom-in-95 duration-150"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-2 pb-3 border-b border-slate-100">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="text-sm font-bold text-slate-900 truncate">
                  {selectedPort.name}
                </h4>
                <span className="inline-flex items-center px-1.5 py-0.5 rounded-sm text-[10px] font-mono font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                  {selectedPort.locode}
                </span>
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">
                {selectedPort.country} · {selectedPort.geofenceRadiusNm} NM Geofence
              </div>
            </div>

            <button
              onClick={() => setSelectedPortId(null)}
              aria-label="Close"
              className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer shrink-0"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* 1-Click Zoom into Port & Alternatives Focus Button */}
          <button
            type="button"
            data-testid="popup-focus-port"
            onClick={() => zoomToCoords(selectedPort.lat, selectedPort.lon, Math.max(zoom, 8))}
            className="w-full mt-2.5 flex items-center justify-center gap-1.5 py-1.5 px-3 bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          >
            <Crosshair className="w-3.5 h-3.5 text-blue-600" />
            <span>Zoom into Port &amp; Alternatives</span>
          </button>

          {/* Risk Badge & Vessel Class */}
          <div className="flex items-center justify-between gap-2 my-2.5">
            {selectedAssessment ? (
              <div
                data-testid="popup-risk-badge"
                className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                  TIER_COLORS[selectedAssessment.compositeTier].bg
                } ${TIER_COLORS[selectedAssessment.compositeTier].text} ${
                  TIER_COLORS[selectedAssessment.compositeTier].border
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    TIER_COLORS[selectedAssessment.compositeTier].dot
                  }`}
                />
                <span>
                  {TIER_LABELS[selectedAssessment.compositeTier].toUpperCase()} ·{' '}
                  {Math.round(selectedAssessment.compositeScore)}
                </span>
              </div>
            ) : (
              <span className="text-xs text-slate-400">Evaluating...</span>
            )}

            <span className="text-[10px] font-semibold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
              {formatVesselClass(vesselClass)}
            </span>
          </div>

          {/* 4-Dimension Traffic Breakdown */}
          {selectedAssessment && (
            <div className="space-y-3">
              <div className="pt-2 border-t border-slate-100">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5 flex items-center justify-between">
                  <span className="flex items-center gap-1">
                    <Ship className="w-3 h-3 text-slate-400" />
                    AIS Traffic Breakdown
                  </span>
                  {selectedAssessment.metrics?.congestion && (
                    <span
                      data-testid="popup-queue-variance"
                      className="text-[10px] font-medium text-slate-600"
                    >
                      {
                        formatQueueVariance(
                          selectedAssessment.metrics.congestion.anchorageQueueCount,
                          selectedAssessment.metrics.congestion.rolling30dAvgQueue
                        ).text
                      }
                    </span>
                  )}
                </div>

                {Boolean((selectedAssessment as any).isColdStart) ||
                Boolean((selectedAssessment as any).isInitializing) ||
                !selectedAssessment.metrics?.congestion ? (
                  <div
                    data-testid="popup-cold-start"
                    className="p-2 bg-blue-50 border border-blue-200 rounded-md text-[11px] font-medium text-blue-800 text-center animate-pulse"
                  >
                    Initializing Live Traffic (Collecting AIS Pings)...
                  </div>
                ) : (
                  <div className="grid grid-cols-3 gap-1.5 text-center bg-slate-50 p-2 rounded-lg border border-slate-200/60">
                    <div>
                      <div className="text-[10px] text-slate-500">Anchored</div>
                      <div
                        data-testid="popup-anchored-count"
                        className="text-xs font-bold text-slate-800"
                      >
                        {selectedAssessment.metrics.congestion.anchorageQueueCount}
                      </div>
                    </div>
                    <div className="border-x border-slate-200">
                      <div className="text-[10px] text-slate-500">Underway</div>
                      <div
                        data-testid="popup-underway-count"
                        className="text-xs font-bold text-slate-800"
                      >
                        {(selectedAssessment.metrics.congestion as any).underwayCount ??
                          0}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-500">Total</div>
                      <div
                        data-testid="popup-total-count"
                        className="text-xs font-bold text-blue-700"
                      >
                        {selectedAssessment.metrics.congestion.anchorageQueueCount +
                          ((selectedAssessment.metrics.congestion as any)
                            .underwayCount ?? 0)}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Depth & Weather Parameters */}
              <div className="pt-2 border-t border-slate-100">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Depth &amp; Weather Parameters
                </div>
                <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                  <div className="p-1.5 bg-slate-50 rounded border border-slate-200/60 flex items-center justify-between">
                    <span className="text-slate-500 flex items-center gap-1">
                      <Compass className="w-3 h-3 text-slate-400" />
                      Depth:
                    </span>
                    {selectedAssessment.metrics.navigational?.channelDepthM !==
                    null ? (
                      <span
                        data-testid="popup-channel-depth"
                        className="font-semibold text-slate-800"
                      >
                        {selectedAssessment.metrics.navigational.channelDepthM.toFixed(
                          1
                        )}
                        m
                      </span>
                    ) : (
                      <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-1 rounded">
                        Depth N/A
                      </span>
                    )}
                  </div>

                  <div className="p-1.5 bg-slate-50 rounded border border-slate-200/60 flex items-center justify-between">
                    <span className="text-slate-500">UKC Margin:</span>
                    <span
                      data-testid="popup-ukc-margin"
                      className={`font-semibold ${
                        selectedAssessment.metrics.navigational
                          .underKeelClearanceM < 0
                          ? 'text-red-600 font-bold'
                          : 'text-emerald-700'
                      }`}
                    >
                      {selectedAssessment.metrics.navigational.underKeelClearanceM > 0
                        ? `+${selectedAssessment.metrics.navigational.underKeelClearanceM.toFixed(
                            1
                          )}m`
                        : `${selectedAssessment.metrics.navigational.underKeelClearanceM.toFixed(
                            1
                          )}m`}{' '}
                      UKC
                    </span>
                  </div>

                  <div className="p-1.5 bg-slate-50 rounded border border-slate-200/60 flex items-center justify-between">
                    <span className="text-slate-500 flex items-center gap-1">
                      <Waves className="w-3 h-3 text-slate-400" />
                      Swell:
                    </span>
                    <span
                      data-testid="popup-swell"
                      className="font-semibold text-slate-800"
                    >
                      {selectedAssessment.metrics.weather?.waveHeightM !== undefined
                        ? `${selectedAssessment.metrics.weather.waveHeightM.toFixed(
                            1
                          )}m Swell`
                        : 'N/A'}
                    </span>
                  </div>

                  <div className="p-1.5 bg-slate-50 rounded border border-slate-200/60 flex items-center justify-between">
                    <span className="text-slate-500 flex items-center gap-1">
                      <Wind className="w-3 h-3 text-slate-400" />
                      Wind:
                    </span>
                    <span
                      data-testid="popup-wind"
                      className="font-semibold text-slate-800"
                    >
                      {selectedAssessment.metrics.weather?.windSpeedKnots !==
                      undefined
                        ? `${selectedAssessment.metrics.weather.windSpeedKnots.toFixed(
                            1
                          )} kn Wind`
                        : 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Inline Alternative Port Diversions (for High Risk only) */}
              <AlternativePortDiversion
                compositeTier={selectedAssessment.compositeTier}
                alternatives={selectedAssessment.alternatives}
                onSelectAlternative={(altId) => {
                  const candidate = selectedAssessment.alternatives?.find(
                    (a) => a.portId === altId || a.unlocode === altId
                  );
                  if (candidate && selectedPort) {
                    setSelectedAlternative({
                      alternative: candidate,
                      primaryPort: selectedPort,
                    });
                    if (typeof candidate.lat === 'number' && typeof candidate.lon === 'number') {
                      zoomToCoords(candidate.lat, candidate.lon, Math.max(zoom, 8));
                    }
                  } else if (onSelectPort) {
                    onSelectPort(altId);
                  }
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* ── Direct On-Map Tooltip Popup for Alternative Safe Haven ── */}
      {selectedAlternative && (
        <div
          role="dialog"
          aria-modal="false"
          aria-label={`Safe Haven Alternative: ${selectedAlternative.alternative.portName}`}
          data-testid="map-alt-popup"
          className="absolute top-4 right-4 z-30 w-84 sm:w-96 max-h-[560px] overflow-y-auto bg-white rounded-xl shadow-2xl border-2 border-cyan-500 p-4 animate-in fade-in zoom-in-95 duration-150"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-2 pb-3 border-b border-cyan-100">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-cyan-100 text-cyan-800 border border-cyan-300">
                  <Compass className="w-3 h-3 text-cyan-600" />
                  RECOMMENDED SAFE HAVEN
                </span>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <h4
                  data-testid="alt-popup-title"
                  className="text-sm font-bold text-slate-900 truncate"
                >
                  {selectedAlternative.alternative.portName}
                </h4>
                <span
                  data-testid="alt-popup-locode"
                  className="inline-flex items-center px-1.5 py-0.5 rounded-sm text-[10px] font-mono font-semibold bg-slate-100 text-slate-700 border border-slate-200"
                >
                  {selectedAlternative.alternative.unlocode}
                </span>
              </div>
              <div
                data-testid="alt-popup-diversion"
                className="text-[11px] text-slate-500 mt-0.5"
              >
                {selectedAlternative.alternative.country} ·{' '}
                <span className="font-semibold text-cyan-700">
                  {selectedAlternative.alternative.distanceNm.toFixed(1)} NM diversion
                </span>{' '}
                from {selectedAlternative.primaryPort.name}
              </div>
            </div>

            <button
              onClick={() => setSelectedAlternative(null)}
              aria-label="Close"
              className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer shrink-0"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* 1-Click Zoom into Safe Haven Focus Button */}
          {typeof selectedAlternative.alternative.lat === 'number' &&
            typeof selectedAlternative.alternative.lon === 'number' && (
              <button
                type="button"
                data-testid="alt-popup-focus"
                onClick={() =>
                  zoomToCoords(
                    selectedAlternative.alternative.lat!,
                    selectedAlternative.alternative.lon!,
                    Math.max(zoom, 8)
                  )
                }
                className="w-full mt-2.5 flex items-center justify-center gap-1.5 py-1.5 px-3 bg-cyan-50 hover:bg-cyan-100 text-cyan-800 border border-cyan-200 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
              >
                <Crosshair className="w-3.5 h-3.5 text-cyan-600" />
                <span>Zoom into Safe Haven</span>
              </button>
            )}

          {/* Clearance & Proximity Stats */}
          <div className="my-3 space-y-2">
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="p-2 bg-emerald-50/80 rounded-lg border border-emerald-200">
                <div className="text-[10px] text-emerald-800 font-semibold uppercase">
                  UKC Margin
                </div>
                <div
                  data-testid="alt-popup-ukc-margin"
                  className="text-sm font-bold text-emerald-700"
                >
                  +{selectedAlternative.alternative.depthMarginM.toFixed(1)}m
                </div>
                <div className="text-[10px] text-emerald-600">Safe draft clearance</div>
              </div>

              <div className="p-2 bg-slate-50 rounded-lg border border-slate-200">
                <div className="text-[10px] text-slate-500 font-semibold uppercase">
                  Controlling Depth
                </div>
                <div
                  data-testid="alt-popup-channel-depth"
                  className="text-sm font-bold text-slate-800"
                >
                  {selectedAlternative.alternative.channelDepthM.toFixed(1)}m
                </div>
                <div className="text-[10px] text-slate-500">Channel baseline</div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="p-2 bg-slate-50 rounded-lg border border-slate-200">
                <div className="text-[10px] text-slate-500 font-semibold uppercase">
                  Swell / Waves
                </div>
                <div
                  data-testid="alt-popup-swell"
                  className="text-xs font-bold text-slate-800"
                >
                  {selectedAlternative.alternative.swellHeightM.toFixed(1)}m Swell
                </div>
              </div>

              <div className="p-2 bg-slate-50 rounded-lg border border-slate-200">
                <div className="text-[10px] text-slate-500 font-semibold uppercase">
                  Queue / Traffic
                </div>
                <div
                  data-testid="alt-popup-traffic"
                  className="text-xs font-bold text-slate-800"
                >
                  {selectedAlternative.alternative.trafficStatus || 'Normal Queue'}
                </div>
              </div>
            </div>
          </div>

          {/* 1-Click + Add to Watchlist Action */}
          {onAddPort && (
            <div className="pt-3 border-t border-slate-100">
              <button
                data-testid="add-alt-to-watchlist"
                disabled={
                  addingAlt ||
                  addedAltLocode === selectedAlternative.alternative.unlocode ||
                  typeof selectedAlternative.alternative.lat !== 'number' ||
                  typeof selectedAlternative.alternative.lon !== 'number'
                }
                onClick={async () => {
                  const alt = selectedAlternative.alternative;
                  if (typeof alt.lat !== 'number' || typeof alt.lon !== 'number') return;
                  setAddingAlt(true);
                  try {
                    await onAddPort({
                      name: alt.portName,
                      locode: alt.unlocode,
                      country: alt.country,
                      lat: alt.lat,
                      lon: alt.lon,
                      geofenceRadiusNm: 25,
                      vesselClass: vesselClass,
                    });
                    setAddedAltLocode(alt.unlocode);
                  } finally {
                    setAddingAlt(false);
                  }
                }}
                className={`w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-bold shadow-sm transition-colors cursor-pointer ${
                  addedAltLocode === selectedAlternative.alternative.unlocode
                    ? 'bg-emerald-600 text-white cursor-default'
                    : 'bg-cyan-600 hover:bg-cyan-700 text-white'
                }`}
              >
                {addedAltLocode === selectedAlternative.alternative.unlocode ? (
                  <>
                    <Check className="w-4 h-4" />
                    <span>Added to Watchlist</span>
                  </>
                ) : (
                  <>
                    <Plus className="w-4 h-4" />
                    <span>+ Add to Watchlist</span>
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
