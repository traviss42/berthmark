import { useState, useEffect, useCallback } from 'react';
import type { Port, VesselClass, RiskAssessment, Notification } from '@/types';
import { getServices } from '@/services';

const MOCK_USER_ID = 'mock-user';

export function usePorts() {
  const [ports, setPorts] = useState<Port[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const services = getServices();

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await services.ports.getPorts(MOCK_USER_ID);
      setPorts(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load ports');
    } finally {
      setLoading(false);
    }
  }, [services]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addPort = useCallback(
    async (port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>) => {
      const created = await services.ports.addPort(port, MOCK_USER_ID);
      setPorts((prev) => [...prev, created]);
      return created;
    },
    [services]
  );

  const removePort = useCallback(
    async (portId: string) => {
      await services.ports.removePort(portId, MOCK_USER_ID);
      setPorts((prev) => prev.filter((p) => p.id !== portId));
    },
    [services]
  );

  return { ports, loading, error, refresh, addPort, removePort };
}

export function useRiskAssessments(
  ports: Port[],
  vesselClass: VesselClass
) {
  const [assessments, setAssessments] = useState<RiskAssessment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const services = getServices();

  const refresh = useCallback(
    async (forceRefresh: boolean = false) => {
      if (ports.length === 0) {
        setAssessments([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await services.risk.getBulkRiskAssessments(
          ports.map((p) => ({ id: p.id, name: p.name })),
          vesselClass,
          forceRefresh
        );
        setAssessments(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load risk data');
      } finally {
        setLoading(false);
      }
    },
    [services, ports, vesselClass]
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { assessments, loading, error, refresh };
}

export function useNotifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const services = getServices();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await services.notifications.getNotifications(MOCK_USER_ID);
      setNotifications(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [services]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const markAsRead = useCallback(
    async (id: string) => {
      await services.notifications.markAsRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read: true } : n))
      );
    },
    [services]
  );

  const markAllAsRead = useCallback(async () => {
    await services.notifications.markAllAsRead(MOCK_USER_ID);
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, [services]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  return { notifications, loading, unreadCount, refresh, markAsRead, markAllAsRead };
}
