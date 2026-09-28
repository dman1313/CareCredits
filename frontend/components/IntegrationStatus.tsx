'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api, publicWebUrl } from '@/lib/portal';

export type ServiceStatus = {
  backend: string;
  database: string;
  database_owner: string;
  frontend: string;
  paid_scrape_ready?: boolean;
  scraper: {
    status: string;
    reachable: boolean;
    tavily_configured: boolean;
    model_ready: boolean;
  };
};

export type IntegrationFlags = {
  model_id: string | null;
  model_publisher: string | null;
  model_host: string | null;
  model_weights_url: string | null;
  model_license_url: string | null;
  model_open_weight_confirmed: boolean;
  model_caps_configured: boolean;
  model_max_input_chars?: number | null;
  model_max_output_tokens?: number | null;
  model_key_configured: boolean;
  typesafe_configured: boolean;
  scraper_token_configured: boolean;
  catalogue_auto_publish_new?: boolean;
};

export function liveDiscoveryReady(
  services: ServiceStatus | null,
  _integrations: IntegrationFlags | null,
) {
  if (typeof services?.paid_scrape_ready === 'boolean') {
    return services.paid_scrape_ready;
  }
  return !!services?.scraper?.tavily_configured && !!services?.scraper?.model_ready;
}

export function IntegrationStatus({
  className = 'small-note',
  onLiveReady,
}: {
  className?: string;
  onLiveReady?: (ready: boolean, loading: boolean) => void;
}) {
  const [integrations, setIntegrations] = useState<IntegrationFlags | null>(null);
  const [services, setServices] = useState<ServiceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const readyRef = useRef(onLiveReady);
  readyRef.current = onLiveReady;

  const load = useCallback(() => {
    setLoading(true);
    readyRef.current?.(false, true);
    setError('');
    Promise.allSettled([api('/admin/services'), api('/admin/integrations')])
      .then(([servicesResult, integrationsResult]) => {
        const nextServices = servicesResult.status === 'fulfilled' ? servicesResult.value : null;
        const nextIntegrations = integrationsResult.status === 'fulfilled' ? integrationsResult.value : null;
        setServices(nextServices);
        setIntegrations(nextIntegrations);
        readyRef.current?.(liveDiscoveryReady(nextServices, nextIntegrations), false);
        if (!nextServices && !nextIntegrations) {
          const first =
            (servicesResult.status === 'rejected' && servicesResult.reason) ||
            (integrationsResult.status === 'rejected' && integrationsResult.reason);
          setError(first instanceof Error ? first.message : 'Status could not be loaded.');
        } else if (!nextServices) {
          setError('Three-service readiness is unavailable. Integration flags below are still from this backend.');
        } else if (!nextIntegrations) {
          setError('Integration status could not be loaded.');
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <p className={className} role="status" aria-busy="true" data-testid="integration-loading">
        Checking service and integration status…
      </p>
    );
  }
  if (!integrations && !services) {
    return error ? (
      <p className={className} role="alert" data-testid="integration-error">
        {error}{' '}
        <button className="text-link" type="button" onClick={load}>
          Retry
        </button>
      </p>
    ) : null;
  }
  const weightsHref = publicWebUrl(integrations?.model_weights_url);
  const licenseHref = publicWebUrl(integrations?.model_license_url);
  return (
    <>
      {error ? (
        <p className={className} role="alert" data-testid="integration-error">
          {error}{' '}
          <button className="text-link" type="button" onClick={load}>
            Retry
          </button>
        </p>
      ) : null}
      {services ? (
        <p className={className} data-testid="service-status">
          Backend {services.backend} · database {services.database} (owned by {services.database_owner}) · scraper{' '}
          {services.scraper.status}
          {services.scraper.reachable ? '' : ' · scraper unreachable'}
          {services.scraper.tavily_configured ? ' · Tavily configured' : ' · Tavily not configured'}
          {services.scraper.model_ready ? ' · model ready' : ' · model not ready'}
          {liveDiscoveryReady(services, integrations)
            ? ' · live discovery ready'
            : ' · live discovery not ready'}{' '}
          · frontend {services.frontend}.
        </p>
      ) : null}
      {integrations ? (
        <p className={className} data-testid="integration-status">
          Model {integrations.model_id || 'not selected'}
          {integrations.model_publisher ? ` · ${integrations.model_publisher}` : ''}
          {integrations.model_host ? ` · ${integrations.model_host}` : ''}
          {integrations.model_open_weight_confirmed ? ' · open-weight confirmed' : ' · open-weight not confirmed'}
          {integrations.model_key_configured ? ' · key present' : ' · key missing'}
          {integrations.model_caps_configured
            ? ` · caps ${integrations.model_max_input_chars || '?'} / ${integrations.model_max_output_tokens || '?'}`
            : ' · caps missing'}
          {integrations.typesafe_configured ? ' · Jev ready' : ' · Jev key missing'}
          {integrations.scraper_token_configured ? ' · scraper token set' : ' · scraper token missing'}
          {integrations.catalogue_auto_publish_new
            ? ' · new events auto-publish'
            : ' · new events await operator publish'}
          .
          {weightsHref ? (
            <>
              {' '}
              <a href={weightsHref} target="_blank" rel="noreferrer">
                Weights
              </a>
            </>
          ) : null}
          {licenseHref ? (
            <>
              {' '}
              <a href={licenseHref} target="_blank" rel="noreferrer">
                Licence
              </a>
            </>
          ) : null}{' '}
          Secrets stay on the server.
        </p>
      ) : null}
    </>
  );
}
