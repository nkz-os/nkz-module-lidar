/**
 * Nekazari SDK - Runtime Bridge
 *
 * This module provides access to the host application's context
 * by connecting to the globals exposed by the host.
 *
 * The host exposes:
 * - window.__nekazariViewerContext.useViewer() - Viewer state hook
 * - window.__nekazariAuth - Authentication state
 * - window.__nekazariUIKit - UI Kit components
 */

// Re-export types from the type declarations
export type {
  ViewerContextValue,
  AuthContextValue,
} from '../types/nekazari-sdk';

/**
 * Access the viewer context from the host application.
 *
 * Provides:
 * - selectedEntityId: Currently selected entity
 * - selectedEntityType: Type of selected entity
 * - selectEntity: Function to select an entity
 * - activeLayers: Set of active map layers
 * - etc.
 */
export function useViewer() {
  const viewerContext = (window as any).__nekazariViewerContext;

  if (!viewerContext || typeof viewerContext.useViewer !== 'function') {
    console.warn('[SDK] ViewerContext not available on window.__nekazariViewerContext');
    // Return a fallback that won't crash but provides no-op functions
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

  // Call the host's useViewer hook
  const result = viewerContext.useViewer();
  console.log('[SDK] useViewer called, selectedEntityId:', result.selectedEntityId);
  return result;
}

/**
 * Access authentication context from the host application.
 *
 * Provides:
 * - user: Current user object
 * - token: JWT token
 * - tenantId: Current tenant ID
 * - isAuthenticated: Boolean authentication status
 * - hasRole: Function to check user roles
 */
export function useAuth() {
  const auth = (window as any).__nekazariAuth;

  if (!auth) {
    console.warn('[SDK] Auth context not available - returning fallback');
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

  // __nekazariAuth is a plain object, not a hook
  return {
    user: auth.user,
    token: auth.token,
    tenantId: auth.tenantId,
    isAuthenticated: !!auth.token,
    hasRole: (role: string) => auth.roles?.includes(role) ?? false,
    hasAnyRole: (roles: string[]) => roles.some(r => auth.roles?.includes(r)),
    getToken: () => auth.token,
  };
}

/**
 * Access translation function from the host application.
 */
export function useTranslation(_namespace?: string) {
  // For now, just return identity function
  // TODO: Connect to host's i18n if available
  return {
    t: (key: string, _params?: Record<string, any>) => key,
    i18n: {
      language: 'es',
    },
  };
}
