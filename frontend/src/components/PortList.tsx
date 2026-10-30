import React, { useMemo } from 'react';
import { Globe, Plus } from 'lucide-react';
import type { Port, RiskAssessment, VesselClass, AlternativePortRecommendation } from '@/types';
import { PortCard } from './PortCard';
import { formatVesselClass } from '@/utils/riskDisplay';

interface Props {
  ports: Port[];
  assessments: Map<string, RiskAssessment>;
  onSelectPort: (portId: string) => void;
  loading: boolean;
  onAddFirstPort?: () => void;
  selectedVesselClass?: VesselClass;
  onRemovePort?: (portId: string) => void;
}

export function PortList({
  ports,
  assessments,
  onSelectPort,
  loading,
  onAddFirstPort,
  selectedVesselClass = 'neoPanamax',
  onRemovePort,
}: Props) {
  // Group ports by assigned vessel class
  const groupedPorts = useMemo(() => {
    const map = new Map<string, Array<{ port: Port; assessment?: RiskAssessment | null }>>();

    ports.forEach((port) => {
      const assessment = assessments.get(port.id);
      const vc =
        (port as any).vesselClass ||
        assessment?.vesselClass ||
        selectedVesselClass ||
        'neoPanamax';

      if (!map.has(vc)) {
        map.set(vc, []);
      }
      map.get(vc)!.push({ port, assessment });
    });

    return map;
  }, [ports, assessments, selectedVesselClass]);

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-slate-200 p-5 bg-white shadow-2xs animate-pulse space-y-4"
          >
            <div className="flex items-start justify-between">
              <div className="space-y-2">
                <div className="h-5 w-36 rounded bg-slate-200" />
                <div className="h-3 w-24 rounded bg-slate-100" />
              </div>
              <div className="h-6 w-20 rounded-full bg-slate-200" />
            </div>
            <div className="h-20 rounded-lg bg-slate-100" />
            <div className="h-16 rounded-lg bg-slate-100" />
          </div>
        ))}
      </div>
    );
  }

  if (ports.length === 0) {
    return (
      <div
        data-testid="empty-port-state"
        className="text-center py-16 px-4 rounded-xl border border-dashed border-slate-300 bg-white"
      >
        <Globe className="w-12 h-12 text-slate-300 mx-auto mb-3" />
        <h3 className="text-sm font-semibold text-slate-700 mb-1">
          No ports currently monitored
        </h3>
        <p className="text-xs text-slate-500 mb-5 max-w-sm mx-auto">
          Your watchlist is currently empty. Add ports to track real-time AIS congestion,
          weather hazards, and depth clearances.
        </p>
        <button
          onClick={onAddFirstPort}
          data-testid="add-first-port-button"
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>+ Add First Port to Watchlist</span>
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {Array.from(groupedPorts.entries()).map(([vc, items]) => (
        <section key={vc} data-testid={`vessel-group-${vc}`} className="space-y-3">
          <div className="flex items-center justify-between border-b border-slate-200 pb-2">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-800">
                {formatVesselClass(vc)}
              </h3>
              <span
                data-testid={`vessel-group-count-${vc}`}
                className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200"
              >
                {items.length} {items.length === 1 ? 'Port' : 'Ports'}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
            {items.map(({ port, assessment }, idx) => (
              <PortCard
                key={`${port.id}-${(port as any).vesselClass || vc}-${idx}`}
                port={port}
                assessment={assessment}
                vesselClass={vc as VesselClass}
                onSelect={onSelectPort}
                onRemove={onRemovePort}
                onSelectAlternative={onSelectPort}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
