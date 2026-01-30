-- =============================================================================
-- LIDAR Module Registration for Nekazari Platform
-- =============================================================================
-- Register the LIDAR module in the platform database
-- Execute: kubectl exec -it -n nekazari $(kubectl get pods -n nekazari -l app=postgresql -o jsonpath='{.items[0].metadata.name}') -- psql -U nekazari -d nekazari -f -
-- =============================================================================

-- Register in marketplace_modules
INSERT INTO marketplace_modules (
    id,
    name,
    display_name,
    description,
    remote_entry_url,
    scope,
    exposed_module,
    version,
    author,
    category,
    icon_url,
    route_path,
    label,
    module_type,
    required_plan_type,
    pricing_tier,
    is_local,
    is_active,
    required_roles,
    metadata
) VALUES (
    'lidar',
    'lidar',
    'LiDAR Point Cloud',
    'Visualize LiDAR point cloud data from PNOA in CesiumJS. Download LAZ files, detect trees, and convert to 3D Tiles for interactive visualization.',
    '/modules/lidar/assets/remoteEntry.js',
    'lidar_module',
    './App',
    '1.0.0',
    'Nekazari Team',
    'analytics',
    NULL,
    '/lidar',
    'LiDAR',
    'ADDON_PAID',
    'premium',
    'PAID',
    false,
    true,
    ARRAY['Farmer', 'TenantAdmin', 'TechnicalConsultant', 'PlatformAdmin'],
    '{
        "icon": "📡",
        "color": "#8B5CF6",
        "shortDescription": "3D point cloud visualization",
        "features": [
            "PNOA LiDAR download",
            "Tree detection and counting",
            "3D Tiles visualization",
            "NDVI colorization",
            "CesiumJS integration"
        ],
        "slots": {
            "layer-toggle": [
                {"id": "lidar-layer-control", "component": "LidarLayerControl", "priority": 10}
            ],
            "map-layer": [
                {"id": "lidar-cesium-layer", "component": "LidarLayer", "priority": 10}
            ],
            "context-panel": [
                {"id": "lidar-config", "component": "LidarConfig", "priority": 20, "showWhen": {"entityType": ["AgriParcel"]}}
            ]
        },
        "navigationItems": [
            {
                "path": "/lidar",
                "label": "LiDAR",
                "icon": "layers"
            }
        ],
        "backend_only": false,
        "backend_url": "http://lidar-api-service:80"
    }'::jsonb
) ON CONFLICT (id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    version = EXCLUDED.version,
    remote_entry_url = EXCLUDED.remote_entry_url,
    scope = EXCLUDED.scope,
    exposed_module = EXCLUDED.exposed_module,
    route_path = EXCLUDED.route_path,
    label = EXCLUDED.label,
    module_type = EXCLUDED.module_type,
    pricing_tier = EXCLUDED.pricing_tier,
    is_active = EXCLUDED.is_active,
    metadata = EXCLUDED.metadata,
    updated_at = NOW();

-- Auto-install for all existing premium tenants (ADDON_PAID)
-- Note: For PAID addons, you'd typically not auto-install
-- This is commented out - enable installation via admin UI
-- INSERT INTO tenant_installed_modules (tenant_id, module_id, is_enabled, configuration)
-- SELECT DISTINCT t.id, 'lidar', true, '{}'::jsonb
-- FROM tenants t WHERE t.plan_type = 'premium'
-- ON CONFLICT (tenant_id, module_id) DO NOTHING;

-- Verify registration
SELECT id, name, display_name, version, is_active, route_path, module_type 
FROM marketplace_modules 
WHERE id = 'lidar';

