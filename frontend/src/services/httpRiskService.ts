import type { RiskAssessment, VesselClass } from '@/types';
import type { IRiskService } from './interfaces';
import { httpClient } from './httpClient';

export class HttpRiskService implements IRiskService {
  async getRiskAssessment(
    portId: string,
    portName: string,
    vesselClass: VesselClass
  ): Promise<RiskAssessment> {
    const params = new URLSearchParams({
      vesselClass,
      portName,
    });
    return httpClient.get<RiskAssessment>(
      `/ports/${encodeURIComponent(portId)}/risk?${params.toString()}`
    );
  }

  async getBulkRiskAssessments(
    ports: { id: string; name: string }[],
    vesselClass: VesselClass
  ): Promise<RiskAssessment[]> {
    return httpClient.post<RiskAssessment[]>('/risk/assessments/bulk', {
      ports,
      vesselClass,
    });
  }

  async getHistoricalTrend(
    portId: string,
    vesselClass: VesselClass,
    days: number
  ): Promise<RiskAssessment[]> {
    const params = new URLSearchParams({
      vesselClass,
      days: days.toString(),
    });
    return httpClient.get<RiskAssessment[]>(
      `/ports/${encodeURIComponent(portId)}/risk/history?${params.toString()}`
    );
  }
}
