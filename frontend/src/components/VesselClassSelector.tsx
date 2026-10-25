import { useState, useEffect, useRef } from 'react';
import { Ship, ChevronDown } from 'lucide-react';
import type { VesselClass } from '@/types';
import { VESSEL_TAXONOMY, SECTORS, getClassesBySector, getVesselClassInfo } from '@/data/vesselTaxonomy';

interface Props {
  value: VesselClass;
  onChange: (cls: VesselClass) => void;
}

export function VesselClassSelector({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = getVesselClassInfo(value);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 transition-colors text-sm"
      >
        <Ship className="w-4 h-4 text-slate-500" />
        <span className="font-medium text-slate-700">{current.label}</span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 z-30 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-xl max-h-96 overflow-y-auto">
          {SECTORS.map((sector) => {
            const classes = getClassesBySector(sector.id);
            return (
              <div key={sector.id} className="border-b border-slate-100 last:border-0">
                <div className="px-4 py-2 text-xs font-semibold text-slate-400 uppercase tracking-wide bg-slate-50/50">
                  {sector.label}
                </div>
                {classes.map((cls) => (
                  <button
                    key={cls.id}
                    onClick={() => {
                      onChange(cls.id);
                      setOpen(false);
                    }}
                    className={`w-full text-left px-4 py-2.5 hover:bg-blue-50 transition-colors ${
                      cls.id === value ? 'bg-blue-50' : ''
                    }`}
                  >
                    <div className="text-sm font-medium text-slate-800">{cls.label}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{cls.criteria}</div>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
