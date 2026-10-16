import type { VesselClass, VesselClassInfo, VesselSector } from '@/types';

export const VESSEL_TAXONOMY: VesselClassInfo[] = [
  // Containerized
  {
    id: 'feeder',
    label: 'Feeder',
    sector: 'containerized',
    criteria: 'Length < 150m, Beam < 25m, Draft < 9m',
    significance: 'Rapid turnarounds, high maneuverability, minimal windage.',
  },
  {
    id: 'panamax',
    label: 'Panamax / Sub-Panamax',
    sector: 'containerized',
    criteria: 'Length 150–290m, Beam ≤ 32.2m, Draft ≤ 12m',
    significance: 'Traditional inter-regional trade routes; legacy lock limits.',
  },
  {
    id: 'neoPanamax',
    label: 'Neo-Panamax',
    sector: 'containerized',
    criteria: 'Length up to 366m, Beam 32.2–51.2m, Draft ≤ 15.2m',
    significance: 'High capacity; expanded canal constraint rules.',
  },
  {
    id: 'ulcv',
    label: 'ULCV (Ultra Large)',
    sector: 'containerized',
    criteria: 'Length > 366m, Beam > 51.2m, Draft > 15m',
    significance: 'Severe wind sailage impact; channel squat & strict depth limits.',
  },
  // Liquid Bulk
  {
    id: 'mrTanker',
    label: 'MR / Handysize Tanker',
    sector: 'liquidBulk',
    criteria: 'DWT 25,000–50,000, Draft < 11m',
    significance: 'Regional product/chemical distribution.',
  },
  {
    id: 'aframax',
    label: 'Aframax',
    sector: 'liquidBulk',
    criteria: 'DWT 80,000–120,000, Draft 12–15m',
    significance: 'Medium-depth crude routes and lightering ops.',
  },
  {
    id: 'suezmax',
    label: 'Suezmax',
    sector: 'liquidBulk',
    criteria: 'DWT 120,000–200,000, Draft up to 16m',
    significance: 'Constrained by canal draft & deep-water channels.',
  },
  {
    id: 'vlcc',
    label: 'VLCC / ULCC',
    sector: 'liquidBulk',
    criteria: 'DWT 200,000+, Draft > 20m',
    significance: 'Deep-draft offshore SPM or deep terminal restrictions.',
  },
  // Dry Bulk
  {
    id: 'handysize',
    label: 'Handysize / Supramax',
    sector: 'dryBulk',
    criteria: 'DWT 10,000–60,000, Draft 9–11m',
    significance: 'Self-sustaining (geared cranes); accesses smaller ports.',
  },
  {
    id: 'panamaxBulk',
    label: 'Panamax (Bulk)',
    sector: 'dryBulk',
    criteria: 'Beam ≤ 32.2m, Draft ≤ 15m',
    significance: 'Major agricultural & coal route standard.',
  },
  {
    id: 'capesize',
    label: 'Capesize',
    sector: 'dryBulk',
    criteria: 'DWT 120,000+, Draft > 17m',
    significance: 'Deep-water mineral export/import terminals only.',
  },
  // Specialized
  {
    id: 'pctc',
    label: 'PCC / PCTC (Car Carriers)',
    sector: 'specialized',
    criteria: 'High air draft (> 40m), High sailage',
    significance: 'Extremely sensitive to lateral crosswinds; strict wind holds.',
  },
  {
    id: 'lng',
    label: 'LNG / LPG Carriers',
    sector: 'specialized',
    criteria: 'Specialized containment profile',
    significance: 'Mandatory safety exclusion zones & tug escorts.',
  },
];

export const SECTORS: { id: VesselSector; label: string }[] = [
  { id: 'containerized', label: 'Containerized Cargo' },
  { id: 'liquidBulk', label: 'Liquid Bulk / Tankers' },
  { id: 'dryBulk', label: 'Dry Bulk' },
  { id: 'specialized', label: 'Specialized' },
];

export function getVesselClassInfo(cls: VesselClass): VesselClassInfo {
  const info = VESSEL_TAXONOMY.find((v) => v.id === cls);
  if (!info) throw new Error(`Unknown vessel class: ${cls}`);
  return info;
}

export function getClassesBySector(sector: VesselSector): VesselClassInfo[] {
  return VESSEL_TAXONOMY.filter((v) => v.sector === sector);
}

// PIANC-based safety thresholds per vessel class.
// Wind cutoffs are stricter for high-sailage classes (PCTC, ULCV).
// UKC limits are stricter for deep-draft classes (Capesize, VLCC).
export const VESSEL_CLASS_THRESHOLDS: Record<
  VesselClass,
  {
    windHighKnots: number;
    windMediumKnots: number;
    ukcHighM: number;
    ukcMediumM: number;
  }
> = {
  feeder:        { windHighKnots: 45, windMediumKnots: 30, ukcHighM: 0.5, ukcMediumM: 1.5 },
  panamax:       { windHighKnots: 40, windMediumKnots: 28, ukcHighM: 0.8, ukcMediumM: 2.0 },
  neoPanamax:    { windHighKnots: 35, windMediumKnots: 25, ukcHighM: 1.0, ukcMediumM: 2.5 },
  ulcv:          { windHighKnots: 28, windMediumKnots: 20, ukcHighM: 1.5, ukcMediumM: 3.0 },
  mrTanker:      { windHighKnots: 45, windMediumKnots: 30, ukcHighM: 0.5, ukcMediumM: 1.5 },
  aframax:       { windHighKnots: 40, windMediumKnots: 28, ukcHighM: 1.0, ukcMediumM: 2.0 },
  suezmax:       { windHighKnots: 38, windMediumKnots: 25, ukcHighM: 1.2, ukcMediumM: 2.5 },
  vlcc:          { windHighKnots: 35, windMediumKnots: 22, ukcHighM: 1.8, ukcMediumM: 3.5 },
  handysize:     { windHighKnots: 45, windMediumKnots: 30, ukcHighM: 0.5, ukcMediumM: 1.5 },
  panamaxBulk:   { windHighKnots: 40, windMediumKnots: 28, ukcHighM: 1.0, ukcMediumM: 2.0 },
  capesize:      { windHighKnots: 35, windMediumKnots: 25, ukcHighM: 1.5, ukcMediumM: 3.0 },
  pctc:          { windHighKnots: 25, windMediumKnots: 18, ukcHighM: 1.0, ukcMediumM: 2.0 },
  lng:           { windHighKnots: 30, windMediumKnots: 22, ukcHighM: 1.2, ukcMediumM: 2.5 },
};
