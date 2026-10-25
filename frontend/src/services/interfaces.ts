import type {
  Port,
  RiskAssessment,
  Notification,
  VesselClass,
  PortMetrics,
} from '@/types';

// ── Service interfaces ──
// All backend calls go through these interfaces.
// The mock implementations satisfy the same contracts.

export interface IPortService {
  getPorts(userId: string): Promise<Port[]>;
  getDefaultPorts(): Promise<Port[]>;
  searchPorts(query: string): Promise<Port[]>;
  addPort(port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>, userId: string): Promise<Port>;
  removePort(portId: string, userId: string): Promise<void>;
}

export interface IRiskService {
  getRiskAssessment(portId: string, portName: string, vesselClass: VesselClass): Promise<RiskAssessment>;
  getBulkRiskAssessments(
    ports: { id: string; name: string }[],
    vesselClass: VesselClass
  ): Promise<RiskAssessment[]>;
  getHistoricalTrend(portId: string, vesselClass: VesselClass, days: number): Promise<RiskAssessment[]>;
}

export interface INotificationService {
  getNotifications(userId: string): Promise<Notification[]>;
  markAsRead(notificationId: string): Promise<void>;
  markAllAsRead(userId: string): Promise<void>;
  generateStateChangeAlert(
    portId: string,
    portName: string,
    newTier: Notification['tier'],
    previousTier: Notification['tier'] | null
  ): Notification;
}

export interface IServices {
  ports: IPortService;
  risk: IRiskService;
  notifications: INotificationService;
}
