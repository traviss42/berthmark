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
