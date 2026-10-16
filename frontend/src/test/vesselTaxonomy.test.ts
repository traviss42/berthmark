import { describe, it, expect } from 'vitest';
import {
  VESSEL_TAXONOMY,
  getVesselClassInfo,
  getClassesBySector,
  VESSEL_CLASS_THRESHOLDS,
} from '@/data/vesselTaxonomy';
import type { VesselClass, VesselSector } from '@/types';

describe('Vessel Taxonomy', () => {
  it('contains 13 vessel classes', () => {
    expect(VESSEL_TAXONOMY).toHaveLength(13);
  });

  it('covers all 4 sectors', () => {
    const sectors = new Set(VESSEL_TAXONOMY.map((v) => v.sector));
    expect(sectors.has('containerized')).toBe(true);
    expect(sectors.has('liquidBulk')).toBe(true);
    expect(sectors.has('dryBulk')).toBe(true);
    expect(sectors.has('specialized')).toBe(true);
  });

  it('each class has required fields', () => {
    VESSEL_TAXONOMY.forEach((cls) => {
      expect(cls.id).toBeTruthy();
      expect(cls.label).toBeTruthy();
      expect(cls.sector).toBeTruthy();
      expect(cls.criteria).toBeTruthy();
      expect(cls.significance).toBeTruthy();
    });
  });

  it('getVesselClassInfo returns correct info', () => {
    const info = getVesselClassInfo('ulcv');
    expect(info.id).toBe('ulcv');
    expect(info.label).toBe('ULCV (Ultra Large)');
    expect(info.sector).toBe('containerized');
  });

  it('getVesselClassInfo throws for unknown class', () => {
    expect(() => getVesselClassInfo('nonexistent' as VesselClass)).toThrow();
  });

  it('getClassesBySector filters correctly', () => {
    const containerClasses = getClassesBySector('containerized');
    expect(containerClasses).toHaveLength(4);
    containerClasses.forEach((c) => expect(c.sector).toBe('containerized'));

    const specialized = getClassesBySector('specialized');
    expect(specialized).toHaveLength(2);
  });

  it('thresholds exist for all vessel classes', () => {
    const allClasses = VESSEL_TAXONOMY.map((v) => v.id);
    allClasses.forEach((cls) => {
      const th = VESSEL_CLASS_THRESHOLDS[cls];
      expect(th).toBeDefined();
      expect(th.windHighKnots).toBeGreaterThan(0);
      expect(th.windMediumKnots).toBeGreaterThan(0);
      expect(th.windHighKnots).toBeGreaterThan(th.windMediumKnots);
      expect(th.ukcHighM).toBeGreaterThan(0);
      expect(th.ukcMediumM).toBeGreaterThan(0);
      expect(th.ukcMediumM).toBeGreaterThan(th.ukcHighM);
    });
  });

  it('PCTC has stricter wind thresholds than feeder', () => {
    expect(VESSEL_CLASS_THRESHOLDS.pctc.windHighKnots).toBeLessThan(
      VESSEL_CLASS_THRESHOLDS.feeder.windHighKnots
    );
  });

  it('VLCC has stricter UKC thresholds than MR tanker', () => {
    expect(VESSEL_CLASS_THRESHOLDS.vlcc.ukcHighM).toBeGreaterThan(
      VESSEL_CLASS_THRESHOLDS.mrTanker.ukcHighM
    );
  });
});
