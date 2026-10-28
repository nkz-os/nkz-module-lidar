/**
 * LIDAR Module API Client
 * 
 * Provides type-safe API calls to the LIDAR backend.
 */

import { API_ORIGIN } from './apiOrigin';

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

export interface ManualDownloadLink {
    series: 'cob3' | 'cob2' | string;
    sec: string;
    name?: string | null;
    url: string;
}

export interface JobStatus {
    job_id: string;
    status: 'pending' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
    progress: number;
    status_message?: string;
    error_message?: string;
    tileset_url?: string;
    tree_count?: number;
    point_count?: number;
    error_code?: string | null;
    manual_download_links?: ManualDownloadLink[] | null;
}

/** Thrown by pollJobStatus when the job ends failed/cancelled; carries the final status. */
export class JobFailedError extends Error {
    status: JobStatus;

    constructor(status: JobStatus) {
        super(status.error_message || 'Processing stopped');
        this.name = 'JobFailedError';
        this.status = status;
    }
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
    z_min?: number;
    z_max?: number;
    /** Vertical datum treatment applied at processing time
     * ("declared" | "compound:EPSG:5782" | null). Layers with a value
     * render correctly at heightOffset 0. */
    vertical_reference?: string | null;
    /** Required attribution/license for the source data (e.g. PNOA). */
    attribution?: string | null;
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

export class ApiError extends Error {
    status: number;
    detail: unknown;
    constructor(message: string, status: number, detail?: unknown) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.detail = detail;
    }
}

export interface DirectUploadInit {
    upload_id: string;
    url: string;
    fields: Record<string, string>;
    expires_in: number;
}

export interface CompleteUploadParams {
    parcel_id: string;
    geometry_wkt?: string;
    config?: Record<string, unknown>;
    source_crs?: string;
    classification_mode?: string;
    has_rgb?: boolean;
}

class LidarApiClient {
    private baseUrl: string;

    constructor() {
        this.baseUrl = `${API_ORIGIN}/api/lidar`;
    }

    private async request<T>(
        endpoint: string,
        options: RequestInit = {}
    ): Promise<T> {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };

        // Merge provided headers
        if (options.headers) {
            const extra = options.headers as Record<string, string>;
            Object.assign(headers, extra);
        }

        // Add tenant ID header
        const authCtx = (window as any).__nekazariAuthContext;
        const tenantId = authCtx?.tenantId;
        if (tenantId) {
            headers['X-Tenant-ID'] = tenantId;
        }

        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            ...options,
            headers,
            credentials: 'include',
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const detail = errorData.detail;
            throw new ApiError(
                typeof detail === 'string' && detail ? detail : `API error: ${response.status}`,
                response.status,
                detail,
            );
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
     * Cancel a running or queued processing job
     */
    async cancelJob(jobId: string): Promise<void> {
        return this.request(`/process/${jobId}/cancel`, {
            method: 'POST',
        });
    }

    /**
     * Poll job status until completion or failure
     */
    async pollJobStatus(
        jobId: string,
        onProgress: (status: JobStatus) => void,
        intervalMs: number = 2000,
        maxAttempts: number = 300, // 10 minutes max
        signal?: AbortSignal,
    ): Promise<JobStatus> {
        let attempts = 0;

        return new Promise((resolve, reject) => {
            const poll = async () => {
                if (signal?.aborted) {
                    reject(new DOMException('Aborted', 'AbortError'));
                    return;
                }

                try {
                    attempts++;
                    const status = await this.getJobStatus(jobId);
                    onProgress(status);

                    if (status.status === 'completed') {
                        resolve(status);
                        return;
                    }

                    if (status.status === 'failed' || status.status === 'cancelled') {
                        reject(new JobFailedError(status));
                        return;
                    }

                    if (attempts >= maxAttempts) {
                        reject(new Error('Processing timed out'));
                        return;
                    }

                    // Continue polling with abort support
                    const timerId = setTimeout(poll, intervalMs);
                    signal?.addEventListener('abort', () => {
                        clearTimeout(timerId);
                        reject(new DOMException('Aborted', 'AbortError'));
                    }, { once: true });
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

    /**
     * Upload a LiDAR file (.LAZ/.LAS)
     */
    async uploadFile(formData: FormData): Promise<ProcessResponse> {
        // For file uploads, we must NOT set Content-Type to application/json
        // Fetch will automatically set it to multipart/form-data with the correct boundary
        
        const authCtx = (window as any).__nekazariAuthContext;
        const tenantId = authCtx?.tenantId;
        const headers: Record<string, string> = {};
        if (tenantId) {
            headers['X-Tenant-ID'] = tenantId;
        }

        const response = await fetch(`${this.baseUrl}/upload`, {
            method: 'POST',
            headers,
            credentials: 'include',
            body: formData,
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Upload error: ${response.status}`);
        }

        return response.json();
    }

    /**
     * Step 1 of the direct upload: ask for a signed form. Throws ApiError with
     * detail 'direct_upload_unavailable' (503) when the deployment has no
     * public storage URL; callers then fall back to uploadFile().
     */
    async initUpload(parcelId: string, filename: string, sizeBytes: number): Promise<DirectUploadInit> {
        return this.request('/uploads/init', {
            method: 'POST',
            body: JSON.stringify({ parcel_id: parcelId, filename, size_bytes: sizeBytes }),
        });
    }

    /**
     * Step 2: POST the file straight to object storage with the signed form.
     * XHR (not fetch) for upload progress. No credentials: the signature authorizes.
     */
    uploadToStorage(
        init: DirectUploadInit,
        file: File,
        onProgress?: (loaded: number, total: number) => void,
        signal?: AbortSignal,
    ): Promise<void> {
        return new Promise<void>((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const form = new FormData();
            Object.entries(init.fields).forEach(([k, v]) => form.append(k, v));
            form.append('file', file); // must be the last field
            xhr.open('POST', init.url);
            xhr.withCredentials = false;
            xhr.upload.onprogress = (ev) => {
                if (ev.lengthComputable) onProgress?.(ev.loaded, ev.total);
            };
            xhr.onload = () => {
                if (xhr.status === 200 || xhr.status === 201 || xhr.status === 204) {
                    resolve();
                    return;
                }
                const xml = xhr.responseText || '';
                const code = /<Code>([^<]*)<\/Code>/.exec(xml)?.[1];
                const msg = /<Message>([^<]*)<\/Message>/.exec(xml)?.[1];
                const detail = [code, msg].filter(Boolean).join(': ');
                reject(new ApiError(
                    `Storage upload failed (${xhr.status})${detail ? `: ${detail}` : ''}`,
                    xhr.status,
                    detail || undefined,
                ));
            };
            xhr.onerror = () => reject(new ApiError('Storage upload failed: network error', 0));
            xhr.onabort = () => reject(new DOMException('Upload aborted', 'AbortError'));
            if (signal) {
                if (signal.aborted) {
                    reject(new DOMException('Upload aborted', 'AbortError'));
                    return;
                }
                signal.addEventListener('abort', () => xhr.abort(), { once: true });
            }
            xhr.send(form);
        });
    }

    /**
     * Step 3: validate the uploaded object and start processing. Safe to call
     * again with source_crs after a 422 (the object is kept server-side).
     * A 409 means the job already exists: its id is returned.
     */
    async completeUpload(uploadId: string, params: CompleteUploadParams): Promise<ProcessResponse> {
        try {
            return await this.request<ProcessResponse>(`/uploads/${uploadId}/complete`, {
                method: 'POST',
                body: JSON.stringify(params),
            });
        } catch (e) {
            if (e instanceof ApiError && e.status === 409) {
                const jobId = (e.detail as { job_id?: string } | undefined)?.job_id;
                if (jobId) return { job_id: jobId, status: 'queued', message: '' } as ProcessResponse;
            }
            throw e;
        }
    }

    // --------------------------------------------------------------------------
    // Jobs List
    // --------------------------------------------------------------------------

    /**
     * List uploaded source files for the tenant
     */
    async listUploads(): Promise<{
        uploads: Array<{ id: string; filename: string; key: string; size_bytes: number; last_modified: string }>;
        total: number;
    }> {
        return this.request('/uploads');
    }

    /**
     * Delete an uploaded source file
     */
    async deleteUpload(uploadId: string): Promise<void> {
        return this.request(`/uploads/${uploadId}`, { method: 'DELETE' });
    }

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
