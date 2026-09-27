'use client';

import { useCallback, useEffect, useState } from 'react';

export type ServiceStatus = {
  backend: string;
  database: string;
  database_owner: string;
  frontend: string;
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

export function IntegrationStatus({ className = 'small-note' }: { className?: string }) {
  const [integrations, setIntegrations] = useState<IntegrationFlags | null>(null);
  const [services, setServices] = useState<ServiceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    const headers = { 'X-Care-Client': '1' };
    Promise.all([
      fetch('/api/v1/admin/services', { credentials: 'include', headers }).then(async (response) => {
        if (!response.ok) throw new Error('Service status could not be loaded.');
        return response.json();
      }),
      fetch('/api/v1/admin/integrations', { credentials: 'include', headers }).then(async (response) => {
        if (!response.ok) throw new Error('Integration status could not be loaded.');
        return response.json();
      }),
    ])
      .then(([nextServices, nextIntegrations]) => {
        setServices(nextServices);
        setIntegrations(nextIntegrations);
      })
      .catch((err) => {
        setServices(null);
        setIntegrations(null);
        setError(err instanceof Error ? err.message : 'Status could not be loaded.');
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
  if (error) {
    return (
      <p className={className} role="alert" data-testid="integration-error">
        {error}{' '}
        <button className="text-link" type="button" onClick={load}>
          Retry
        </button>
      </p>
    );
  }
  if (!integrations && !services) return null;
  return (
    <>
      {services ? (
        <p className={className} data-testid="service-status">
          Backend {services.backend} · database {services.database} (owned by {services.database_owner}) · scraper{' '}
          {services.scraper.status}
          {services.scraper.reachable ? '' : ' · scraper unreachable'}
          {services.scraper.tavily_configured ? ' · Tavily configured' : ' · Tavily not configured'}
          {services.scraper.model_ready ? ' · model ready' : ' · model not ready'} · frontend {services.frontend}.
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
          {integrations.model_weights_url ? (
            <>
              {' '}
              <a href={integrations.model_weights_url} target="_blank" rel="noreferrer">
                Weights
              </a>
            </>
          ) : null}
          {integrations.model_license_url ? (
            <>
              {' '}
              <a href={integrations.model_license_url} target="_blank" rel="noreferrer">
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
