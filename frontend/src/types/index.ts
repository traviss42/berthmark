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
  vesselClass?: VesselClass;
}

export interface CongestionMetrics {
  anchorageQueueCount: number;
  avgWaitingTimeHours: number;
  berthOccupancyPct: number;
  rolling30dAvgQueue: number | null;
  rolling30dAvgWaitHours: number | null;
}

export interface TerminalMetrics {
  berthTurnaroundHours: number;
  berthToAnchorageWaitRatio: number;
  dwellTimeAnomalyScore: number;
  rolling30dAvgTurnaround: number;
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
  airDraftClearanceM: number;
  pilotageAvailable: boolean;
  tideHeightM: number;
}

export interface PortMetrics {
  portId: string;
  timestamp: string;
  congestion: CongestionMetrics;
  weather: WeatherMetrics;
  navigational: NavigationalMetrics;
  terminal?: TerminalMetrics;
}

export interface SubRiskResult {
  category: SubRiskCategory;
  tier: RiskTier;
  score: number;
  detail: string;
  factors: string[];
}

export interface AlternativePortRecommendation {
  portId: string;
  unlocode: string;
  portName: string;
  country: string;
  distanceNm: number;
  channelDepthM: number;
  depthMarginM: number;
  swellHeightM: number;
  riskTier: RiskTier;
  trafficStatus?: string;
  lat?: number;
  lon?: number;
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
  alternatives?: AlternativePortRecommendation[];
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
}

export interface RiskThresholds {
  congestion: {
    queueAnomalyRatio: number;
    waitAnomalyRatio: number;
    berthOccupancyHighPct: number;
    berthOccupancyMediumPct: number;
  };
  terminal: {
    turnaroundAnomalyRatio: number;
    waitRatioHigh: number;
    waitRatioMedium: number;
    dwellAnomalyHigh: number;
    dwellAnomalyMedium: number;
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
    airDraftClearanceLowM: number;
    airDraftClearanceMediumM: number;
  };
}

// ── Authentication & User models ──

export interface User {
  id: string;
  email: string;
  name?: string;
  createdAt?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  name?: string;
  email: string;
  password: string;
}

export interface AuthResponse {
  accessToken: string;
  tokenType: string;
  expiresIn?: number;
  user: User;
}

export interface ErrorResponse {
  error: string;
  message: string;
  statusCode: number;
}

export interface ApiError extends Error {
  error: string;
  statusCode: number;
}

