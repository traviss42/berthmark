import type { Port } from '@/types';
import type { IPortService } from './interfaces';
import { httpClient } from './httpClient';

export class HttpPortService implements IPortService {
  async getPorts(_userId?: string): Promise<Port[]> {
    return httpClient.get<Port[]>('/ports');
  }

  async getDefaultPorts(): Promise<Port[]> {
    return httpClient.get<Port[]>('/ports/default');
  }

  async searchPorts(query: string): Promise<Port[]> {
    if (!query || !query.trim()) {
      return [];
    }
    const encoded = encodeURIComponent(query.trim());
    return httpClient.get<Port[]>(`/ports/search?q=${encoded}`);
  }

  async addPort(
    port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>,
    _userId?: string
  ): Promise<Port> {
    return httpClient.post<Port>('/ports', port);
  }

  async removePort(portId: string, _userId?: string): Promise<void> {
    await httpClient.delete<void>(`/ports/${encodeURIComponent(portId)}`);
  }
}
