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
 */

import { createContext, useContext, type Context } from 'react';
import type { ViewerHookResult } from '../types';


// Re-export types
export type { ViewerHookResult as ViewerContextValue } from '../types';
export type { NekazariAuthContext as AuthContextValue } from '../types';

// Stable fallback context, created once at module load. Used when the host
// has not exposed __nekazariViewerContextInstance yet (eg. standalone dev).
const FallbackViewerContext = createContext<ViewerHookResult | undefined>(undefined);

const EMPTY_VIEWER: ViewerHookResult = {
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

/**
 * Access the viewer context from the host application.
 *
 * The host exposes its ViewerContext object on window. Module Federation 2.0
 * makes React a shared singleton, so calling useContext from this module hits
 * the same provider chain the host sets up.
 */
export function useViewer(): ViewerHookResult {
  const HostViewerContext =
    (window as any).__nekazariViewerContextInstance as
      | Context<ViewerHookResult | undefined>
      | undefined;
  const ctx = useContext(HostViewerContext ?? FallbackViewerContext);
  return ctx ?? EMPTY_VIEWER;
}

/**
 * Access authentication context from the host application.
 * Auth is handled via httpOnly cookie — no token exposed to JS.
 */
export function useAuth() {
  // Auth is handled via httpOnly cookie. Token is no longer exposed.
  // Read auth state from host context (no token/getToken).
  const auth = (window as any).__nekazariAuthContext;
  if (auth?.isAuthenticated) {
    return {
      user: auth.user ?? null,
      tenantId: auth.tenantId as string | undefined,
      isAuthenticated: true,
      hasRole: (role: string) => auth.roles?.includes(role) ?? false,
      hasAnyRole: (roles: string[]) => roles.some((r: string) => auth.roles?.includes(r)),
    };
  }

  return {
    user: null,
    tenantId: undefined as string | undefined,
    isAuthenticated: false,
    hasRole: () => false,
    hasAnyRole: () => false,
  };
}

/**
 * Translation hook bound to the host's shared i18next instance (namespace `lidar`,
 * registered in ../i18n.ts), so the module follows the language the user picked.
 */
export { useTranslation } from '@nekazari/sdk';
