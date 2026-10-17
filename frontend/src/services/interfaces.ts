import type {
  Port,
  RiskAssessment,
  Notification,
  VesselClass,
  User,
  AuthResponse,
  StreamStatus,
} from '@/types';

// ── Service interfaces ──
// All backend calls go through these interfaces.

export interface IPortService {
  getPorts(userId: string, vesselClass?: VesselClass): Promise<Port[]>;
  getDefaultPorts(): Promise<Port[]>;
  searchPorts(query: string): Promise<Port[]>;
  addPort(port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>, userId: string): Promise<Port>;
  removePort(portId: string, userId: string): Promise<void>;
  updatePortNotifications(portId: string, notificationsEnabled: boolean, userId?: string): Promise<Port>;
}

export interface IRiskService {
  getRiskAssessment(
    portId: string,
    portName: string,
    vesselClass: VesselClass,
    forceRefresh?: boolean
  ): Promise<RiskAssessment>;
  getBulkRiskAssessments(
    ports: { id: string; name: string; vesselClass?: VesselClass }[],
    vesselClass: VesselClass,
    forceRefresh?: boolean
  ): Promise<RiskAssessment[]>;
  getHistoricalTrend(
    portId: string,
    vesselClass: VesselClass,
    days: number,
    forceRefresh?: boolean
  ): Promise<RiskAssessment[]>;
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

export interface IAuthService {
  login(email: string, password?: string): Promise<AuthResponse>;
  getCurrentUser(token?: string): Promise<User>;
  logout(): Promise<void>;
}

export interface ISystemService {
  getStreamStatus(): Promise<StreamStatus>;
}

export interface IServices {
  ports: IPortService;
  risk: IRiskService;
  notifications: INotificationService;
  auth: IAuthService;
  system: ISystemService;
}
