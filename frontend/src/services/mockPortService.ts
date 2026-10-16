import type { Port } from '@/types';
import type { IPortService } from '@/services/interfaces';
import { DEFAULT_PORTS } from '@/data/mockData';

// Additional ports for search simulation
const SEARCHABLE_PORTS: Port[] = [
  { id: 'port-antwerp', name: 'Port of Antwerp-Bruges', locode: 'BEANR', country: 'Belgium', lat: 51.3, lon: 4.3, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-hongkong', name: 'Port of Hong Kong', locode: 'HKHKG', country: 'Hong Kong', lat: 22.3, lon: 114.2, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-busan', name: 'Port of Busan', locode: 'KRPUS', country: 'South Korea', lat: 35.1, lon: 129.0, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-savannah', name: 'Port of Savannah', locode: 'USSAV', country: 'United States', lat: 32.1, lon: -81.1, isDefault: false, geofenceRadiusNm: 7, addedByUserId: null },
  { id: 'port-longbeach', name: 'Port of Long Beach', locode: 'USLGB', country: 'United States', lat: 33.8, lon: -118.2, isDefault: false, geofenceRadiusNm: 7, addedByUserId: null },
  { id: 'port-tanjungpelepas', name: 'Tanjung Pelepas', locode: 'MYTPP', country: 'Malaysia', lat: 1.4, lon: 103.5, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-jawaharnehru', name: 'Jawaharlal Nehru Port', locode: 'INNSA', country: 'India', lat: 18.9, lon: 72.9, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-suez', name: 'Suez Canal Port', locode: 'EGSUZ', country: 'Egypt', lat: 30.0, lon: 32.5, isDefault: false, geofenceRadiusNm: 10, addedByUserId: null },
  { id: 'port-piraeus', name: 'Port of Piraeus', locode: 'GRPIR', country: 'Greece', lat: 37.9, lon: 23.6, isDefault: false, geofenceRadiusNm: 7, addedByUserId: null },
  { id: 'port-valencia', name: 'Port of Valencia', locode: 'ESVLC', country: 'Spain', lat: 39.4, lon: -0.3, isDefault: false, geofenceRadiusNm: 7, addedByUserId: null },
  { id: 'port-santos', name: 'Port of Santos', locode: 'BRSSZ', country: 'Brazil', lat: -23.9, lon: -46.3, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-durban', name: 'Port of Durban', locode: 'ZADUR', country: 'South Africa', lat: -29.9, lon: 31.0, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-ningbo', name: 'Port of Ningbo-Zhoushan', locode: 'CNNGB', country: 'China', lat: 29.8872, lon: 121.5622, isDefault: false, geofenceRadiusNm: 10, addedByUserId: null },
  { id: 'port-shenzhen', name: 'Port of Shenzhen', locode: 'CNSZX', country: 'China', lat: 22.5033, lon: 113.8967, isDefault: false, geofenceRadiusNm: 9, addedByUserId: null },
  { id: 'port-guangzhou', name: 'Port of Guangzhou', locode: 'CNGZG', country: 'China', lat: 23.0967, lon: 113.4333, isDefault: false, geofenceRadiusNm: 9, addedByUserId: null },
  { id: 'port-qingdao', name: 'Port of Qingdao', locode: 'CNTAO', country: 'China', lat: 36.0833, lon: 120.3167, isDefault: false, geofenceRadiusNm: 9, addedByUserId: null },
  { id: 'port-tianjin', name: 'Port of Tianjin', locode: 'CNTSN', country: 'China', lat: 38.9833, lon: 117.75, isDefault: false, geofenceRadiusNm: 9, addedByUserId: null },
  { id: 'port-portklang', name: 'Port Klang', locode: 'MYPKG', country: 'Malaysia', lat: 3.0, lon: 101.4, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-kaohsiung', name: 'Port of Kaohsiung', locode: 'TWKHH', country: 'Taiwan', lat: 22.6167, lon: 120.2833, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-felixstowe', name: 'Port of Felixstowe', locode: 'GBFXT', country: 'United Kingdom', lat: 51.9567, lon: 1.3094, isDefault: false, geofenceRadiusNm: 7, addedByUserId: null },
  { id: 'port-algeciras', name: 'Port of Algeciras', locode: 'ESALG', country: 'Spain', lat: 36.1333, lon: -5.4333, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-bremerhaven', name: 'Port of Bremerhaven', locode: 'DEBRV', country: 'Germany', lat: 53.55, lon: 8.5833, isDefault: false, geofenceRadiusNm: 7, addedByUserId: null },
  { id: 'port-barcelona', name: 'Port of Barcelona', locode: 'ESBCN', country: 'Spain', lat: 41.35, lon: 2.1667, isDefault: false, geofenceRadiusNm: 7, addedByUserId: null },
  { id: 'port-lehavre', name: 'Port of Le Havre', locode: 'FRLEH', country: 'France', lat: 49.4833, lon: 0.1167, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-genoa', name: 'Port of Genoa', locode: 'ITGOA', country: 'Italy', lat: 44.4167, lon: 8.9167, isDefault: false, geofenceRadiusNm: 7, addedByUserId: null },
  { id: 'port-southampton', name: 'Port of Southampton', locode: 'GBSOU', country: 'United Kingdom', lat: 50.9, lon: -1.4, isDefault: false, geofenceRadiusNm: 7, addedByUserId: null },
  { id: 'port-newyork', name: 'Port of New York and New Jersey', locode: 'USNYC', country: 'United States', lat: 40.6667, lon: -74.1167, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-houston', name: 'Port of Houston', locode: 'USHOU', country: 'United States', lat: 29.75, lon: -95.2667, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-seattle', name: 'Port of Seattle', locode: 'USSEA', country: 'United States', lat: 47.6, lon: -122.35, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-vancouver', name: 'Port of Vancouver', locode: 'CAVAN', country: 'Canada', lat: 49.3, lon: -123.1167, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-colon', name: 'Port of Colon (Manzanillo / Cristobal)', locode: 'PAONX', country: 'Panama', lat: 9.35, lon: -79.9, isDefault: false, geofenceRadiusNm: 9, addedByUserId: null },
  { id: 'port-balboa', name: 'Port of Balboa', locode: 'PABLB', country: 'Panama', lat: 8.95, lon: -79.5667, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-salalah', name: 'Port of Salalah', locode: 'OMSLL', country: 'Oman', lat: 16.95, lon: 54.0167, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-jeddah', name: 'Jeddah Islamic Port', locode: 'SAJED', country: 'Saudi Arabia', lat: 21.4667, lon: 39.1667, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-alexandria', name: 'Port of Alexandria', locode: 'EGALY', country: 'Egypt', lat: 31.2, lon: 29.8667, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-sydney', name: 'Port of Sydney (Port Botany)', locode: 'AUSYD', country: 'Australia', lat: -33.9667, lon: 151.2167, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-melbourne', name: 'Port of Melbourne', locode: 'AUMEL', country: 'Australia', lat: -37.8333, lon: 144.9167, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
  { id: 'port-auckland', name: 'Port of Auckland', locode: 'NZAKL', country: 'New Zealand', lat: -36.85, lon: 174.7833, isDefault: false, geofenceRadiusNm: 8, addedByUserId: null },
];

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class MockPortService implements IPortService {
  private userPorts: Map<string, Port[]> = new Map();

  async getPorts(userId: string): Promise<Port[]> {
    await delay(150);
    const userAdded = this.userPorts.get(userId) ?? [];
    return [...DEFAULT_PORTS, ...userAdded];
  }

  async getDefaultPorts(): Promise<Port[]> {
    await delay(80);
    return [...DEFAULT_PORTS];
  }

  async searchPorts(query: string): Promise<Port[]> {
    await delay(200);
    const q = query.toLowerCase().trim();
    if (!q) return [];
    const all = [...DEFAULT_PORTS, ...SEARCHABLE_PORTS];
    const seen = new Set<string>();
    return all.filter((p) => {
      if (seen.has(p.id)) return false;
      seen.add(p.id);
      return (
        p.name.toLowerCase().includes(q) ||
        p.locode.toLowerCase().includes(q) ||
        p.country.toLowerCase().includes(q)
      );
    });
  }

  async addPort(port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>, userId: string): Promise<Port> {
    await delay(250);
    const newPort: Port = {
      ...port,
      id: `port-user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      isDefault: false,
      addedByUserId: userId,
    };
    const existing = this.userPorts.get(userId) ?? [];
    this.userPorts.set(userId, [...existing, newPort]);
    return newPort;
  }

  async removePort(portId: string, userId: string): Promise<void> {
    await delay(150);
    const existing = this.userPorts.get(userId) ?? [];
    this.userPorts.set(
      userId,
      existing.filter((p) => p.id !== portId)
    );
  }
}
