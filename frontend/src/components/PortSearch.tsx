import { useState, useEffect, useRef } from 'react';
import { Search, MapPin, Plus, X, Ship } from 'lucide-react';
import type { Port, VesselClass } from '@/types';
import { getServices } from '@/services';
import { VESSEL_TAXONOMY } from '@/data/vesselTaxonomy';

export interface SubscriptionRef {
  locode: string;
  vesselClass?: string;
}

interface Props {
  onAddPort: (port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>) => Promise<unknown>;
  existingLocodes?: string[];
  existingSubscriptions?: SubscriptionRef[];
  defaultVesselClass?: VesselClass;
}

export function PortSearch({
  onAddPort,
  existingLocodes = [],
  existingSubscriptions,
  defaultVesselClass = 'neoPanamax',
}: Props) {
  const [query, setQuery] = useState('');
  const [selectedVesselClass, setSelectedVesselClass] = useState<VesselClass>(defaultVesselClass);
  const [results, setResults] = useState<Port[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const services = getServices();

  useEffect(() => {
    if (defaultVesselClass) {
      setSelectedVesselClass(defaultVesselClass);
    }
  }, [defaultVesselClass]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const ports = await services.ports.searchPorts(query);
        setResults(ports);
        setOpen(true);
      } catch (err) {
        console.error('Failed to search ports:', err);
        setResults([]);
        setOpen(true);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query, services]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const isPortAlreadyAdded = (locode: string): boolean => {
    if (existingSubscriptions && existingSubscriptions.length > 0) {
      return existingSubscriptions.some(
        (sub) =>
          sub.locode.toUpperCase() === locode.toUpperCase() &&
          (sub.vesselClass || 'neoPanamax').toLowerCase() === selectedVesselClass.toLowerCase()
      );
    }
    return existingLocodes.includes(locode);
  };

  async function handleAdd(port: Port) {
    setAdding(true);
    try {
      await onAddPort({
        name: port.name,
        locode: port.locode,
        country: port.country,
        lat: port.lat,
        lon: port.lon,
        geofenceRadiusNm: port.geofenceRadiusNm,
        vesselClass: selectedVesselClass,
      });
      setQuery('');
      setResults([]);
      setOpen(false);
    } finally {
      setAdding(false);
    }
  }

  return (
    <div ref={containerRef} className="relative w-full">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          id="port-search-input"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Search ports by name, LOCODE, or country..."
          className="w-full pl-10 pr-4 py-2.5 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400 transition-all"
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setResults([]); setOpen(false); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {open && (loading || results.length > 0) && (
        <div className="absolute z-20 mt-2 w-full rounded-lg border border-slate-200 bg-white shadow-lg max-h-80 overflow-y-auto">
          {/* Vessel class assignment header */}
          <div className="sticky top-0 z-10 px-3.5 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between gap-2 flex-wrap text-xs">
            <span className="font-semibold text-slate-700 flex items-center gap-1.5">
              <Ship className="w-3.5 h-3.5 text-blue-600" />
              <span>Target Class:</span>
            </span>
            <select
              data-testid="search-vessel-class-select"
              value={selectedVesselClass}
              onChange={(e) => setSelectedVesselClass(e.target.value as VesselClass)}
              className="px-2 py-1 bg-white border border-slate-300 rounded text-xs font-semibold text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer shadow-2xs"
            >
              {VESSEL_TAXONOMY.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label} ({opt.criteria})
                </option>
              ))}
            </select>
          </div>

          {loading && (
            <div className="px-4 py-3 text-sm text-slate-400">Searching...</div>
          )}
          {!loading && results.map((port) => {
            const alreadyAdded = isPortAlreadyAdded(port.locode);
            return (
              <div
                key={port.id}
                className="flex items-center justify-between px-4 py-2.5 hover:bg-slate-50 border-b border-slate-100 last:border-0 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <MapPin className="w-4 h-4 text-slate-400 flex-shrink-0" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-800 truncate">{port.name}</div>
                    <div className="text-xs text-slate-500">{port.locode} · {port.country}</div>
                  </div>
                </div>
                <button
                  onClick={() => handleAdd(port)}
                  disabled={alreadyAdded || adding}
                  className="flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-md bg-blue-50 text-blue-600 hover:bg-blue-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
                >
                  <Plus className="w-3.5 h-3.5" />
                  {alreadyAdded ? 'Added' : 'Add'}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {open && !loading && query.trim().length >= 2 && results.length === 0 && (
        <div className="absolute z-20 mt-2 w-full rounded-lg border border-slate-200 bg-white shadow-lg px-4 py-3 text-sm text-slate-400">
          No ports found. Try a different name or LOCODE.
        </div>
      )}
    </div>
  );
}
