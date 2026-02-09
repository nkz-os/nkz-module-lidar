/**
 * Nekazari SDK - Runtime Bridge
 *
 * This module provides access to the host application's context
 * by connecting to the globals exposed by the host.
 *
 * The host exposes:
 * - window.__nekazariViewerContext.useViewer() - Viewer state hook
 * - window.__nekazariAuth / __nekazariAuthContext - Authentication state
 * - window.__nekazariUIKit - UI Kit components
 * - window.__nekazariI18n - i18n context
 */

import type { ViewerHookResult } from '../types';

// Import locale files for standalone fallback
import esLocale from '../locales/es.json';
import enLocale from '../locales/en.json';
import euLocale from '../locales/eu.json';
import caLocale from '../locales/ca.json';
import frLocale from '../locales/fr.json';
import ptLocale from '../locales/pt.json';

const locales: Record<string, Record<string, string>> = {
  es: esLocale,
  en: enLocale,
  eu: euLocale,
  ca: caLocale,
  fr: frLocale,
  pt: ptLocale,
};

// Re-export types
export type { ViewerHookResult as ViewerContextValue } from '../types';
export type { NekazariAuthContext as AuthContextValue } from '../types';

/**
 * Access the viewer context from the host application.
 */
export function useViewer(): ViewerHookResult {
  const viewerContext = window.__nekazariViewerContext;

  if (!viewerContext || typeof viewerContext.useViewer !== 'function') {
    if (import.meta.env.DEV) {
      console.warn('[SDK] ViewerContext not available on window.__nekazariViewerContext');
    }
    return {
      selectedEntityId: null,
      selectedEntityType: null,
      currentDate: new Date(),
      isTimelinePlaying: false,
      activeLayers: new Set(),
      isLayerActive: () => false,
      setLayerActive: () => {},
      toggleLayer: () => {},
      selectEntity: () => {},
      setCurrentDate: () => {},
    };
  }

  return viewerContext.useViewer();
}

/**
 * Access authentication context from the host application.
 *
 * Checks: window.__nekazariAuthContext, window.__nekazariAuth,
 * window.keycloak, localStorage fallback.
 */
export function useAuth() {
  const auth = window.__nekazariAuthContext ?? window.__nekazariAuth;

  if (auth?.token) {
    return {
      user: auth.user,
      token: auth.token,
      tenantId: auth.tenantId,
      isAuthenticated: true,
      hasRole: (role: string) => auth.roles?.includes(role) ?? false,
      hasAnyRole: (roles: string[]) => roles.some(r => auth.roles?.includes(r)),
      getToken: () => auth.token,
    };
  }

  // Keycloak fallback
  const kc = window.keycloak;
  if (kc?.token) {
    return {
      user: kc.tokenParsed ?? null,
      token: kc.token,
      tenantId: undefined,
      isAuthenticated: true,
      hasRole: () => false,
      hasAnyRole: () => false,
      getToken: () => kc.token,
    };
  }

  // localStorage fallback
  const storedToken = localStorage.getItem('nkz_token');
  if (storedToken) {
    return {
      user: null,
      token: storedToken,
      tenantId: localStorage.getItem('nkz_tenant_id') ?? undefined,
      isAuthenticated: true,
      hasRole: () => false,
      hasAnyRole: () => false,
      getToken: () => storedToken,
    };
  }

  if (import.meta.env.DEV) {
    console.warn('[SDK] Auth context not available - returning fallback');
  }
  return {
    user: null,
    token: undefined,
    tenantId: undefined,
    isAuthenticated: false,
    hasRole: () => false,
    hasAnyRole: () => false,
    getToken: () => undefined,
  };
}

/**
 * Access translation function from the host application.
 * Falls back to local JSON files if host i18n is unavailable (standalone mode).
 */
export function useTranslation(_namespace?: string) {
  // Try host's i18n context first
  const hostI18n = window.__nekazariI18n;
  if (hostI18n) {
    return {
      t: (key: string, params?: Record<string, string | number>) => {
        let result = hostI18n.t(`lidar.${key}`, params as Record<string, string>);
        // If host returned the full key, it doesn't have our namespace — use local
        if (result === `lidar.${key}`) {
          result = localTranslate(hostI18n.i18n.language, key, params);
        }
        return result;
      },
      i18n: hostI18n.i18n,
    };
  }

  // Standalone mode: use local locale files
  const lang = detectLanguage();
  return {
    t: (key: string, params?: Record<string, string | number>) =>
      localTranslate(lang, key, params),
    i18n: { language: lang },
  };
}

function detectLanguage(): string {
  // Check localStorage, then navigator
  const stored = localStorage.getItem('i18nextLng');
  if (stored && locales[stored]) return stored;
  const nav = navigator.language?.split('-')[0];
  if (nav && locales[nav]) return nav;
  return 'es';
}

function localTranslate(
  lang: string,
  key: string,
  params?: Record<string, string | number>
): string {
  const dict = locales[lang] ?? locales['es'];
  let value = dict[key] ?? locales['es'][key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      value = value.replace(`{{${k}}}`, String(v));
    }
  }
  return value;
}
