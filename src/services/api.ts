/**
 * LIDAR Module API Client
 * 
 * Provides type-safe API calls to the LIDAR backend.
 */

// ============================================================================
// Types
// ============================================================================

export interface ProcessingConfig {
    colorize_by: 'height' | 'ndvi' | 'rgb' | 'classification';
    detect_trees: boolean;
    tree_min_height: number;
    tree_search_radius: number;
    ndvi_source_url?: string;
}

export interface ProcessRequest {
    parcel_id: string;
    parcel_geometry_wkt: string;
    config: ProcessingConfig;
}

export interface ProcessResponse {
    job_id: string;
    status: string;
    message: string;
}

export interface JobStatus {
    job_id: string;
    status: 'pending' | 'queued' | 'processing' | 'completed' | 'failed';
    progress: number;
    status_message?: string;
    error_message?: string;
    tileset_url?: string;
    tree_count?: number;
    point_count?: number;
}

export interface CoverageResponse {
    has_coverage: boolean;
    tiles: CoverageTile[];
}

export interface CoverageTile {
    id: string;
    tile_name: string;
    source: string;
    flight_year?: number;
    point_density?: number;
    laz_url: string;
}

export interface Layer {
    id: string;
    parcel_id: string;
    tileset_url: string;
    source: string;
    point_count?: number;
    date_observed?: string;
}

export interface DetectedTree {
    id: string;
    location: {
        type: 'Point';
        coordinates: [number, number];
    };
    height: number;
    crown_diameter: number;
    crown_area: number;
}

// ============================================================================
// API Client Class
// ============================================================================

class LidarApiClient {
    private baseUrl: string;
    private getToken: () => string | null;

    constructor() {
        // Base URL from environment or default
        this.baseUrl = '/api/lidar';
        this.getToken = () => {
            // Try to get token from global context (injected by host)
            return window.__nekazariAuth?.token ?? null;
        };
    }

    private async request<T>(
        endpoint: string,
        options: RequestInit = {}
    ): Promise<T> {
        const token = this.getToken();
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };

        // Merge provided headers
        if (options.headers) {
            const extra = options.headers as Record<string, string>;
            Object.assign(headers, extra);
        }

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            ...options,
            headers,
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `API error: ${response.status}`);
        }

        return response.json();
    }

    // --------------------------------------------------------------------------
    // Coverage Check
    // --------------------------------------------------------------------------

    /**
     * Check if LiDAR coverage is available for a geometry
     */
    async checkCoverage(geometryWkt: string, source?: string): Promise<CoverageResponse> {
        return this.request('/coverage', {
            method: 'POST',
            body: JSON.stringify({
                geometry_wkt: geometryWkt,
                source,
            }),
        });
    }

    // --------------------------------------------------------------------------
    // Processing Jobs
    // --------------------------------------------------------------------------

    /**
     * Start a new processing job
     */
    async startProcessing(request: ProcessRequest): Promise<ProcessResponse> {
        return this.request('/process', {
            method: 'POST',
            body: JSON.stringify(request),
        });
    }

    /**
     * Get job status
     */
    async getJobStatus(jobId: string): Promise<JobStatus> {
        return this.request(`/status/${jobId}`);
    }

    /**
     * Poll job status until completion or failure
     */
    async pollJobStatus(
        jobId: string,
        onProgress: (status: JobStatus) => void,
        intervalMs: number = 2000,
        maxAttempts: number = 300 // 10 minutes max
    ): Promise<JobStatus> {
        let attempts = 0;

        return new Promise((resolve, reject) => {
            const poll = async () => {
                try {
                    attempts++;
                    const status = await this.getJobStatus(jobId);
                    onProgress(status);

                    if (status.status === 'completed') {
                        resolve(status);
                        return;
                    }

                    if (status.status === 'failed') {
                        reject(new Error(status.error_message || 'Processing failed'));
                        return;
                    }

                    if (attempts >= maxAttempts) {
                        reject(new Error('Processing timed out'));
                        return;
                    }

                    // Continue polling
                    setTimeout(poll, intervalMs);
                } catch (error) {
                    reject(error);
                }
            };

            poll();
        });
    }

    // --------------------------------------------------------------------------
    // Layers
    // --------------------------------------------------------------------------

    /**
     * Get all layers for the tenant
     */
    async getLayers(parcelId?: string): Promise<Layer[]> {
        const params = parcelId ? `?parcel_id=${encodeURIComponent(parcelId)}` : '';
        return this.request(`/layers${params}`);
    }

    /**
     * Get a specific layer
     */
    async getLayer(layerId: string): Promise<Layer> {
        return this.request(`/layers/${layerId}`);
    }

    /**
     * Delete a layer
     */
    async deleteLayer(layerId: string): Promise<void> {
        return this.request(`/layers/${layerId}`, {
            method: 'DELETE',
        });
    }

    // --------------------------------------------------------------------------
    // Jobs List
    // --------------------------------------------------------------------------

    /**
     * List processing jobs
     */
    async listJobs(options?: {
        status?: string;
        parcelId?: string;
        limit?: number;
        offset?: number;
    }): Promise<{
        jobs: Array<{
            id: string;
            parcel_id: string;
            status: string;
            progress: number;
            created_at: string;
            completed_at?: string;
        }>;
        total: number;
    }> {
        const params = new URLSearchParams();
        if (options?.status) params.set('status_filter', options.status);
        if (options?.parcelId) params.set('parcel_id', options.parcelId);
        if (options?.limit) params.set('limit', options.limit.toString());
        if (options?.offset) params.set('offset', options.offset.toString());

        const queryString = params.toString();
        return this.request(`/jobs${queryString ? '?' + queryString : ''}`);
    }
}

// Export singleton instance
export const lidarApi = new LidarApiClient();

// Export default config
export const DEFAULT_PROCESSING_CONFIG: ProcessingConfig = {
    colorize_by: 'height',
    detect_trees: false,
    tree_min_height: 2.0,
    tree_search_radius: 3.0,
};
