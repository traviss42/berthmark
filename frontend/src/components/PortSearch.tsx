import { useState, useEffect, useRef } from 'react';
import { Search, MapPin, Plus, X } from 'lucide-react';
import type { Port } from '@/types';
import { getServices } from '@/services';

interface Props {
  onAddPort: (port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>) => Promise<unknown>;
  existingLocodes: string[];
}

export function PortSearch({ onAddPort, existingLocodes }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Port[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const services = getServices();

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setSearchError(null);
      return;
    }
    setLoading(true);
    setSearchError(null);
    const timer = setTimeout(async () => {
      try {
        const ports = await services.ports.searchPorts(q);
        setResults(ports);
        setOpen(true);
      } catch (err) {
        setSearchError(err instanceof Error ? err.message : 'Search failed');
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

      {open && (loading || results.length > 0 || searchError || (!loading && query.trim().length > 0)) && (
        <div className="absolute z-20 mt-2 w-full rounded-lg border border-slate-200 bg-white shadow-lg max-h-72 overflow-y-auto">
          {loading && (
            <div className="px-4 py-3 text-sm text-slate-400">Searching...</div>
          )}
          {searchError && (
            <div className="px-4 py-3 text-sm text-red-600 bg-red-50">
              {searchError}
            </div>
          )}
          {!loading && !searchError && results.map((port) => {
            const alreadyAdded = existingLocodes.includes(port.locode);
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
          {open && !loading && !searchError && query.trim().length > 0 && results.length === 0 && (
            <div className="px-4 py-3 text-sm text-slate-400">
              No ports found. Try a different name or UN/LOCODE.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
