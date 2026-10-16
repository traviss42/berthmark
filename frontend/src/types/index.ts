// ── Core domain types for the Port-Call Risk Tracking application ──

export type RiskTier = 'low' | 'medium' | 'high';

export type SubRiskCategory =
  | 'congestion'
  | 'weather'
  | 'navigational';

export type VesselSector =
  | 'containerized'
  | 'liquidBulk'
  | 'dryBulk'
  | 'specialized';

export type VesselClass =
  // Containerized
  | 'feeder'
  | 'panamax'
  | 'neoPanamax'
  | 'ulcv'
  // Liquid Bulk
  | 'mrTanker'
  | 'aframax'
  | 'suezmax'
  | 'vlcc'
  // Dry Bulk
  | 'handysize'
  | 'panamaxBulk'
  | 'capesize'
  // Specialized
  | 'pctc'
  | 'lng';

export interface VesselClassInfo {
  id: VesselClass;
  label: string;
  sector: VesselSector;
  criteria: string;
  significance: string;
}

export interface Port {
  id: string;
  name: string;
  locode: string;
  country: string;
  lat: number;
  lon: number;
  isDefault: boolean;
  geofenceRadiusNm: number;
  addedByUserId: string | null;
  notificationsEnabled?: boolean;
  channelDepthM?: number | null;
  cargoPierDepthM?: number | null;
  anchorageDepthM?: number | null;
  oilTerminalDepthM?: number | null;
  lngTerminalDepthM?: number | null;
  maxVesselDraftM?: number | null;
  tidalRangeM?: number | null;
  overheadLimits?: string | null;
  pilotageAvailable?: boolean | null;
  tugsAssistance?: boolean | null;
  harborSize?: string | null;
  shelterAfforded?: string | null;
}

export interface CongestionMetrics {
  anchorageQueueCount: number;
  activeVesselCount: number;
  movingVesselCount: number;
  rolling30dAvgQueue: number;
}

export interface WeatherMetrics {
  windSpeedKnots: number;
  waveHeightM: number;
  swellPeriodSec: number;
  visibilityNm: number;
  gustSpeedKnots: number;
}

export interface NavigationalMetrics {
  underKeelClearanceM: number;
  channelDepthM: number;
  cargoPierDepthM?: number | null;
  anchorageDepthM?: number | null;
  vesselDraftM: number;
  overheadLimits: string;
  pilotageAvailable: boolean;
  tugsAssistance: boolean;
  tideHeightM: number;
  harborSize?: string | null;
  shelterAfforded?: string | null;
}

export interface PortMetrics {
  portId: string;
  timestamp: string;
  congestion: CongestionMetrics;
  weather: WeatherMetrics;
  navigational: NavigationalMetrics;
}

export interface SubRiskResult {
  category: SubRiskCategory;
  tier: RiskTier;
  score: number;
  detail: string;
  factors: string[];
}

export interface RiskAssessment {
  id: string;
  portId: string;
  portName: string;
  vesselClass: VesselClass;
  vesselClassLabel: string;
  timestamp: string;
  compositeTier: RiskTier;
  compositeScore: number;
  subRisks: Record<SubRiskCategory, SubRiskResult>;
  metrics: PortMetrics;
}

export type NotificationType = 'stateChange' | 'dailyDigest' | 'inApp';

export interface Notification {
  id: string;
  type: NotificationType;
  portId: string;
  portName: string;
  title: string;
  message: string;
  tier: RiskTier;
  previousTier: RiskTier | null;
  timestamp: string;
  read: boolean;
  recipientEmail?: string | null;
}

export interface User {
  id: string;
  email: string;
  name?: string;
}

export interface AuthResponse {
  accessToken: string;
  tokenType: string;
  user: User;
}

export interface RiskThresholds {
  congestion: {
    queueAnomalyRatio: number;
    queueHighCount: number;
    queueMediumCount: number;
  };
  weather: {
    windHighKnots: number;
    windMediumKnots: number;
    waveHighM: number;
    waveMediumM: number;
    visibilityLowNm: number;
    visibilityMediumNm: number;
  };
  navigational: {
    ukcHighM: number;
    ukcMediumM: number;
  };
}

