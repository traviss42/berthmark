import type { RiskAssessment, VesselClass } from '@/types';
import type { IRiskService } from '@/services/interfaces';
import { generateMockMetrics } from '@/data/mockData';
import { assessRisk } from '@/services/riskEngine';

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class MockRiskService implements IRiskService {
  async getRiskAssessment(
    portId: string,
    portName: string,
    vesselClass: VesselClass
  ): Promise<RiskAssessment> {
    await delay(300);
    const metrics = generateMockMetrics(portId, vesselClass);
    return assessRisk(portId, portName, vesselClass, metrics);
  }

  async getBulkRiskAssessments(
    ports: { id: string; name: string }[],
    vesselClass: VesselClass
  ): Promise<RiskAssessment[]> {
    await delay(400);
    return ports.map((p) => {
      const metrics = generateMockMetrics(p.id, vesselClass);
      return assessRisk(p.id, p.name, vesselClass, metrics);
    });
  }

  async getHistoricalTrend(
    portId: string,
    vesselClass: VesselClass,
    days: number
  ): Promise<RiskAssessment[]> {
    await delay(350);
    const assessments: RiskAssessment[] = [];
    const now = Date.now();
    const sixHourMs = 6 * 60 * 60 * 1000;
    const points = Math.min(days * 4, 40); // 4 evaluations per day (6-hour cycle), cap at 40

    for (let i = points - 1; i >= 0; i--) {
      const ts = new Date(now - i * sixHourMs).toISOString();
      // Use a time-shifted seed for variety
      const metrics = generateMockMetrics(`${portId}-${i}`, vesselClass);
      metrics.timestamp = ts;
      const portName = '';
      assessments.push(assessRisk(portId, portName, vesselClass, metrics));
    }
    return assessments;
  }
}
