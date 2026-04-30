# LiDAR Classification & Canopy Structure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve LAS `Classification`, `ReturnNumber`, `NumberOfReturns` through the pipeline, compute `HeightAboveGround` via PDAL filters.hag, pass all 4 fields to py3dtiles, and expose 6 color modes with an inline legend in the Cesium viewer.

**Architecture:** PDAL `filters.hag` computes HeightAboveGround after crop+denoise. py3dtiles receives `--extra-fields` for all 4 attributes. Frontend replaces the static COLOR_RAMPS with a Cesium3DTileStyle per mode, adds a dynamic legend, and shows a classification-mode modal on drone upload.

**Tech Stack:** Python 3.12, PDAL (filters.smrf, filters.hag), py3dtiles 7.0.0, Cesium 1.136 3D Tiles Styling, React 18 + TypeScript 5, i18next (6 locales)

**Spec:** `docs/superpowers/specs/2026-04-30-lidar-classification-design.md`

---

## Task 1: Add PY3DTILES_EXTRA_FIELDS to config

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add config field**

```python
# In class Settings, add after TILING_TARGET_POINTS:
PY3DTILES_EXTRA_FIELDS: list = ["Classification", "ReturnNumber", "NumberOfReturns", "HeightAboveGround"]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(lidar): add PY3DTILES_EXTRA_FIELDS config"
```

---

## Task 2: Compute HeightAboveGround and preserve extra fields in Phase A

**Files:**
- Modify: `backend/app/services/lidar_pipeline.py`

- [ ] **Step 1: Add filters.hag after existing crop+denoise in phase_a_ingest**

In `phase_a_ingest()`, after the existing PDAL pipeline that writes `cropped.laz`, add a second PDAL pipeline that:

1. Reads `cropped.laz`
2. Runs `filters.smrf` (classifies ground if not already classified — idempotent on pre-classified data)
3. Runs `filters.hag` (computes HeightAboveGround dimension)
4. Writes back to `cropped.laz`

Insert after `logger.info(f"Phase A complete. {count} points. Output: {self.cropped_laz}")` (approximately line 258):

```python
# Compute HeightAboveGround via PDAL filters.hag
# smrf classifies ground (no-op if already classified), hag computes height above ground
hag_pipeline = {
    "pipeline": [
        {"type": "readers.las", "filename": self.cropped_laz},
        {"type": "filters.smrf"},
        {"type": "filters.hag"},
        {
            "type": "writers.las",
            "filename": self.cropped_laz,
            "compression": "laszip",
            "extra_dims": "HeightAboveGround=float",
        },
    ]
}
pdal.Pipeline(json.dumps(hag_pipeline)).execute()
logger.info("Phase A HAG: HeightAboveGround computed and stored")
```

- [ ] **Step 2: Verify smrf + hag output is valid LAS**

The output must preserve all original dimensions PLUS add `HeightAboveGround`. laspy can verify:

```python
# Verify step (manual, not committed)
import laspy
with laspy.open("cropped.laz") as f:
    print(f"Point format: {f.header.point_format}")
    for dim in f.header.point_format.dimensions:
        print(f"  {dim.name}: {dim.kind}")
```

Expected: `HeightAboveGround` appears as a float dimension alongside X, Y, Z, Classification, etc.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/lidar_pipeline.py
git commit -m "feat(lidar): compute HeightAboveGround via PDAL filters.smrf + filters.hag"
```

---

## Task 3: Pass extra fields to py3dtiles in Phase D

**Files:**
- Modify: `backend/app/services/lidar_pipeline.py`

- [ ] **Step 1: Add --extra-fields flags to py3dtiles command**

In `phase_d_tiling()`, update the py3dtiles command (around line 544). The current command:

```python
cmd = [
    py3dtiles_bin, "convert",
    source_laz,
    "--out", self.output_tiles_dir,
    "--overwrite"
]
```

Add extra fields from config:

```python
cmd = [
    py3dtiles_bin, "convert",
    source_laz,
    "--out", self.output_tiles_dir,
    "--overwrite"
]
# Preserve LAS classification and structure attributes for Cesium styling
for field in settings.PY3DTILES_EXTRA_FIELDS:
    cmd.extend(["--extra-fields", field])
```

- [ ] **Step 2: Verify the tileset output preserves extra dimensions**

After conversion, inspect the tileset.json feature table to confirm extra fields are present:

```bash
python3 -c "
import json
with open('tileset.json') as f:
    data = json.load(f)
# Check root tile for extra fields in batch table or feature table
print(json.dumps(data['root'].get('content', {}), indent=2))
"
```

Expected: the batch table or feature table JSON should reference `Classification`, `ReturnNumber`, `NumberOfReturns`, `HeightAboveGround`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/lidar_pipeline.py
git commit -m "feat(lidar): pass extra LAS fields to py3dtiles for Cesium styling"
```

---

## Task 4: Auto-classify unclassified drone uploads

**Files:**
- Modify: `backend/app/services/lidar_pipeline.py`

- [ ] **Step 1: Detect and classify unclassified inputs**

In `phase_a_ingest()`, before the HAG step, check if the input has `Classification`. If not (or all values are 0), run `filters.smrf` to generate ground classification.

Add after the initial PDAL crop+denoise, before HAG (around line 258):

```python
# Auto-classify if the input lacks classification (common for drone uploads)
needs_classification = False
try:
    with laspy.open(self.cropped_laz) as reader:
        # Check if Classification dimension exists and has non-zero values
        has_class = any(
            dim.name.lower() == "classification"
            for dim in reader.header.point_format.dimensions
        )
        if has_class:
            las = reader.read()
            unique_classes = set(int(c) for c in las.classification)
            needs_classification = len(unique_classes) <= 1 and 0 in unique_classes
        else:
            needs_classification = True
except Exception:
    needs_classification = True

if needs_classification:
    logger.info("Input lacks classification — auto-classifying with PDAL smrf")
    classify_pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": self.cropped_laz},
            {"type": "filters.smrf"},
            {"type": "filters.hag"},
            {
                "type": "writers.las",
                "filename": self.cropped_laz,
                "compression": "laszip",
                "extra_dims": "HeightAboveGround=float",
            },
        ]
    }
    pdal.Pipeline(json.dumps(classify_pipeline)).execute()
    logger.info("Auto-classification complete")
else:
    # Already classified — just run HAG
    hag_pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": self.cropped_laz},
            {"type": "filters.smrf"},
            {"type": "filters.hag"},
            {
                "type": "writers.las",
                "filename": self.cropped_laz,
                "compression": "laszip",
                "extra_dims": "HeightAboveGround=float",
            },
        ]
    }
    pdal.Pipeline(json.dumps(hag_pipeline)).execute()
    logger.info("HAG computed on pre-classified data")
```

Note: `filters.smrf` is idempotent — running it on already-classified data preserves existing classes. The `filters.hag` filter needs `Classification` to identify ground points (class 2); smrf ensures they exist.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/lidar_pipeline.py
git commit -m "feat(lidar): auto-classify unclassified drone uploads with PDAL smrf"
```

---

## Task 5: Accept classification_mode and has_rgb in upload API

**Files:**
- Modify: `backend/app/api/lidar.py`

- [ ] **Step 1: Add classification_mode and has_rgb to upload endpoint**

In `upload_laz_file()`, add two new Form fields after `source_crs`:

```python
classification_mode: Optional[str] = Form(
    default="detect",
    description="native=use file classes, auto=always recompute, detect=auto if missing"
),
has_rgb: Optional[bool] = Form(default=True, description="Whether the LAZ has RGB color data"),
```

- [ ] **Step 2: Pass fields through to config**

Add to the `config_payload` dict (around line 423):

```python
config_payload = {
    **config_dict,
    "uploaded_file_path": s3_key,
    "source": "user_upload",
    "source_crs": source_crs,
    "classification_mode": classification_mode,
    "has_rgb": has_rgb,
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/lidar.py
git commit -m "feat(lidar): accept classification_mode and has_rgb in upload endpoint"
```

---

## Task 6: Replace color ramps with 6 visualization modes

**Files:**
- Modify: `src/components/slots/LidarLayer.tsx`

- [ ] **Step 1: Define the 6 color modes with proper Cesium 3D Tiles style expressions**

Replace the entire `COLOR_RAMPS` constant (lines 40-78) with:

```typescript
const COLOR_RAMPS: Record<string, string> = {
  height: `
    float t = clamp((\${POSITION}[2] - 0.0) / 50.0, 0.0, 1.0);
    float r = t < 0.5 ? 0.0 : (t - 0.5) * 2.0;
    float g = t < 0.5 ? t * 2.0 : 2.0 - t * 2.0;
    float b = 1.0 - t;
    color(r, g, b, 1.0)
  `,

  classification: `
    float c = \${Classification};
    if (c == 2.0) { color(0.55, 0.35, 0.15, 1.0) }           // ground
    else if (c == 3.0) { color(0.0, 0.7, 0.1, 1.0) }          // low vegetation
    else if (c == 4.0) { color(0.0, 0.65, 0.0, 1.0) }         // medium vegetation
    else if (c == 5.0) { color(0.0, 0.5, 0.0, 1.0) }          // high vegetation
    else if (c == 6.0) { color(0.7, 0.7, 0.7, 1.0) }          // building
    else if (c == 9.0) { color(0.0, 0.3, 0.8, 1.0) }          // water
    else { color(0.9, 0.9, 0.9, 1.0) }                         // unclassified / other
  `,

  heightAboveGround: `
    float h = \${HeightAboveGround};
    float t = clamp(h / 5.0, 0.0, 1.0);
    float r = t < 0.33 ? t * 2.0 : (t < 0.66 ? 1.0 : 1.0);
    float g = t < 0.33 ? 0.5 + t : (t < 0.66 ? 1.0 : 2.0 - t);
    float b = t < 0.33 ? 0.0 : 0.0;
    color(r, g, b, 1.0)
  `,

  canopyCover: `
    float h = \${HeightAboveGround};
    float rn = \${ReturnNumber};
    if (rn > 1.0 && h < 1.5) { color(0.2, 0.8, 0.2, 1.0) }    // understory cover
    else if (h > 2.5) { color(0.0, 0.4, 0.1, 1.0) }           // canopy top
    else if (h < 0.3) { color(0.55, 0.35, 0.15, 1.0) }        // bare ground
    else { color(0.4, 0.7, 0.1, 1.0) }                         // mid vegetation
  `,

  verticalDensity: `
    float h = \${HeightAboveGround};
    float d = clamp(h / 8.0, 0.0, 1.0);
    float r = d;
    float g = 1.0 - d;
    color(r, g, 0.0, 1.0)
  `,

  rgb: `
    vec4 c = \${COLOR};
    color(c.r, c.g, c.b, 1.0)
  `,
};
```

- [ ] **Step 2: Update the color mode options in LidarLayerToggle and LidarLayerControl**

In `LidarLayerToggle.tsx`, replace the `COLOR_MODES` constant:

```typescript
const COLOR_MODES: { value: ColorMode; icon: string }[] = [
  { value: 'height', icon: '📏' },
  { value: 'classification', icon: '🏷️' },
  { value: 'heightAboveGround', icon: '📐' },
  { value: 'canopyCover', icon: '🌿' },
  { value: 'verticalDensity', icon: '📊' },
  { value: 'rgb', icon: '🎨' },
];
```

In `LidarLayerControl.tsx`, update `COLOR_MODE_OPTIONS` (around line 91) with the same 6 modes plus description strings:

```typescript
const COLOR_MODE_OPTIONS: { value: ColorMode; label: string; icon: string; desc: string }[] = [
  { value: 'height', label: t('color.height'), icon: '📏', desc: t('color.height.desc') },
  { value: 'classification', label: t('color.classification'), icon: '🏷️', desc: t('color.classification.desc') },
  { value: 'heightAboveGround', label: t('color.hag'), icon: '📐', desc: t('color.hag.desc') },
  { value: 'canopyCover', label: t('color.canopy'), icon: '🌿', desc: t('color.canopy.desc') },
  { value: 'verticalDensity', label: t('color.density'), icon: '📊', desc: t('color.density.desc') },
  { value: 'rgb', label: t('color.rgb'), icon: '🎨', desc: t('color.rgb.desc') },
];
```

- [ ] **Step 3: Update the ColorMode type in lidarContext.tsx**

```typescript
export type ColorMode = 'height' | 'classification' | 'heightAboveGround' | 'canopyCover' | 'verticalDensity' | 'rgb';
```

- [ ] **Step 4: Update the lidarStore default colorMode**

```typescript
public colorMode: ColorMode = 'height';
```

(Keep the default, just ensure the type union includes all 6 values.)

- [ ] **Step 5: Commit**

```bash
git add src/components/slots/LidarLayer.tsx src/components/slots/LidarLayerToggle.tsx src/components/slots/LidarLayerControl.tsx src/services/lidarContext.tsx src/services/lidarStore.ts
git commit -m "feat(lidar): add 6 color modes with LAS classification and canopy structure"
```

---

## Task 7: Add inline legend bar below color pills

**Files:**
- Modify: `src/components/slots/LidarLayerControl.tsx`

- [ ] **Step 1: Define legend data per color mode**

Add a `LEGENDS` constant before the component:

```typescript
const LEGENDS: Record<ColorMode, Array<{ color: string; label: string }>> = {
  height: [
    { color: '#0000ff', label: '0m' },
    { color: '#00ff00', label: '25m' },
    { color: '#ff0000', label: '50m+' },
  ],
  classification: [
    { color: '#8B5E3C', label: 'Suelo' },
    { color: '#00B31A', label: 'Vegetación' },
    { color: '#B3B3B3', label: 'Edificio' },
  ],
  heightAboveGround: [
    { color: '#8B5E3C', label: '0m' },
    { color: '#FFFF00', label: '1m' },
    { color: '#00FF00', label: '3m' },
    { color: '#FF0000', label: '5m+' },
  ],
  canopyCover: [
    { color: '#33CC33', label: 'Cubierta' },
    { color: '#006B00', label: 'Copa' },
    { color: '#8B5E3C', label: 'Suelo' },
  ],
  verticalDensity: [
    { color: '#0000ff', label: 'Baja' },
    { color: '#ffff00', label: 'Media' },
    { color: '#ff0000', label: 'Alta' },
  ],
  rgb: [],
};
```

- [ ] **Step 2: Render legend below color mode pills in active layer section**

After the color pills div (after line ~492), add:

```tsx
{LEGENDS[colorMode].length > 0 && (
  <div className="flex gap-2 mt-2 text-[10px] text-slate-500">
    {LEGENDS[colorMode].map((item, i) => (
      <span key={i} className="flex items-center gap-1">
        <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: item.color }} />
        {item.label}
      </span>
    ))}
  </div>
)}
```

- [ ] **Step 3: Commit**

```bash
git add src/components/slots/LidarLayerControl.tsx
git commit -m "feat(lidar): add inline color legend below mode pills"
```

---

## Task 8: Upload classification modal

**Files:**
- Modify: `src/components/slots/LidarLayerControl.tsx`

- [ ] **Step 1: Add state for classification mode and RGB checkbox**

```typescript
const [classificationMode, setClassificationMode] = useState<'native' | 'auto' | 'detect'>('detect');
const [hasRgb, setHasRgb] = useState(true);
const [showUploadOptions, setShowUploadOptions] = useState(false);
```

- [ ] **Step 2: Modify handleFileUpload to show options before uploading**

Replace the current `handleFileUpload` logic: after parsing the LAZ header, if the file passes validation, show the options modal instead of uploading immediately.

```typescript
const handleFileUpload = async (file: File) => {
    // ... existing validation (extension, size) ...
    
    // Parse header (existing worker code)
    const parserWorker = new LazWorker();
    const headerInfo: LazHeaderParseResult = await new Promise((resolve, reject) => {
        parserWorker.onmessage = (ev) => resolve(ev.data as LazHeaderParseResult);
        parserWorker.onerror = (err) => reject(err);
        parserWorker.postMessage({ file });
        setTimeout(() => reject(new Error('Worker timeout')), 5000);
    });
    parserWorker.terminate();

    if (!headerInfo.hasProjectionVlr && !manualCrs.trim()) {
        setRequiresManualCrs(true);
        throw new Error(t('errorMissingCrs'));
    }

    // Store file reference and show options
    setPendingFile(file);
    setShowUploadOptions(true);
};
```

Add `pendingFile` state:

```typescript
const [pendingFile, setPendingFile] = useState<File | null>(null);
```

- [ ] **Step 3: Add the actual upload function**

```typescript
const doUpload = async () => {
    if (!pendingFile) return;
    const file = pendingFile;
    setShowUploadOptions(false);
    setPendingFile(null);
    setIsUploading(true);

    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('parcel_id', selectedEntityId || 'unknown');
        if (selectedEntityGeometry) formData.append('geometry_wkt', selectedEntityGeometry);
        formData.append('config', JSON.stringify(processingConfig));
        formData.append('classification_mode', classificationMode);
        if (hasRgb) formData.append('has_rgb', 'true');
        if (manualCrs.trim()) formData.append('source_crs', manualCrs.trim());

        const uploadResponse = await lidarApi.uploadFile(formData);
        const finalStatus = await lidarApi.pollJobStatus(
            uploadResponse.job_id,
            (status) => setUploadJobStatus({ progress: status.progress, message: status.status_message || '' }),
            2000, 300,
        );
        if (finalStatus.tileset_url) await refreshLayers();
        setUploadJobStatus(null);
    } catch (error: unknown) {
        setUploadJobStatus(null);
        const msg = error instanceof Error ? error.message : t('errorUpload');
        setErrorWithTimeout(msg);
    } finally {
        setIsUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = '';
    }
};
```

- [ ] **Step 4: Add the modal UI**

After the error display section, add:

```tsx
{showUploadOptions && (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowUploadOptions(false)}>
        <div className="bg-white rounded-xl p-5 shadow-xl max-w-sm w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-slate-800 mb-3">{t('uploadClassification')}</h3>

            <label className="flex items-center gap-2 mb-2 text-sm cursor-pointer">
                <input type="radio" name="classMode" value="native" checked={classificationMode === 'native'}
                    onChange={() => setClassificationMode('native')} />
                {t('classificationNative')}
            </label>
            <label className="flex items-center gap-2 mb-2 text-sm cursor-pointer">
                <input type="radio" name="classMode" value="auto" checked={classificationMode === 'auto'}
                    onChange={() => setClassificationMode('auto')} />
                {t('classificationAuto')}
            </label>
            <label className="flex items-center gap-2 mb-4 text-sm cursor-pointer">
                <input type="radio" name="classMode" value="detect" checked={classificationMode === 'detect'}
                    onChange={() => setClassificationMode('detect')} />
                {t('classificationDetect')}
            </label>

            <label className="flex items-center gap-2 mb-4 text-sm cursor-pointer">
                <input type="checkbox" checked={hasRgb} onChange={(e) => setHasRgb(e.target.checked)} />
                {t('hasRgb')}
            </label>

            <div className="flex gap-2">
                <button onClick={doUpload} className="flex-1 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium">
                    {t('continue')}
                </button>
                <button onClick={() => { setShowUploadOptions(false); setPendingFile(null); }}
                    className="flex-1 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-sm">
                    {t('cancel')}
                </button>
            </div>
        </div>
    </div>
)}
```

- [ ] **Step 5: Commit**

```bash
git add src/components/slots/LidarLayerControl.tsx
git commit -m "feat(lidar): add upload classification options modal"
```

---

## Task 9: i18n keys for all 6 locales

**Files:**
- Modify: `src/locales/en.json`
- Modify: `src/locales/es.json`
- Modify: `src/locales/ca.json`
- Modify: `src/locales/eu.json`
- Modify: `src/locales/fr.json`
- Modify: `src/locales/pt.json`

- [ ] **Step 1: Add keys to en.json**

```json
"color.hag": "Crop Height",
"color.hag.desc": "Height above ground",
"color.canopy": "Canopy vs Cover",
"color.canopy.desc": "Tree crown vs understory",
"color.density": "Density",
"color.density.desc": "Vertical structure proxy",
"uploadClassification": "Classification",
"classificationNative": "Already classified (PNOA, DJI Terra, Pix4D...)",
"classificationAuto": "Unclassified — auto-classify",
"classificationDetect": "I don't know — detect automatically",
"hasRgb": "Has RGB color",
"continue": "Continue",
"cancel": "Cancel"
```

- [ ] **Step 2: Add keys to es.json**

```json
"color.hag": "Altura Cultivo",
"color.hag.desc": "Altura sobre el suelo",
"color.canopy": "Copa vs Cubierta",
"color.canopy.desc": "Copa del árbol vs sotobosque",
"color.density": "Densidad",
"color.density.desc": "Proxy de estructura vertical",
"uploadClassification": "Clasificación",
"classificationNative": "Ya viene clasificado (PNOA, DJI Terra, Pix4D...)",
"classificationAuto": "Sin clasificar — auto-clasificar",
"classificationDetect": "No lo sé — detectar automáticamente",
"hasRgb": "Tiene color RGB",
"continue": "Continuar",
"cancel": "Cancelar"
```

- [ ] **Step 3: Add keys to eu.json**

```json
"color.hag": "Laboreren Altuera",
"color.hag.desc": "Lurraren gaineko altuera",
"color.canopy": "Kopa vs Estaldura",
"color.canopy.desc": "Zuhaitz kopa vs sastraka",
"color.density": "Dentsitatea",
"color.density.desc": "Egitura bertikalaren hurbilketa",
"uploadClassification": "Sailkapena",
"classificationNative": "Dagoeneko sailkatua (PNOA, DJI Terra, Pix4D...)",
"classificationAuto": "Sailkatu gabe — auto-sailkatu",
"classificationDetect": "Ez dakit — automatikoki detektatu",
"hasRgb": "RGB kolorea du",
"continue": "Jarraitu",
"cancel": "Utzi"
```

- [ ] **Step 4: Add keys to ca.json**

```json
"color.hag": "Alçada del Cultiu",
"color.hag.desc": "Alçada sobre el sòl",
"color.canopy": "Copa vs Cobertura",
"color.canopy.desc": "Copa d'arbre vs sotabosc",
"color.density": "Densitat",
"color.density.desc": "Proxy d'estructura vertical",
"uploadClassification": "Classificació",
"classificationNative": "Ja ve classificat (PNOA, DJI Terra, Pix4D...)",
"classificationAuto": "Sense classificar — auto-classificar",
"classificationDetect": "No ho sé — detectar automàticament",
"hasRgb": "Té color RGB",
"continue": "Continuar",
"cancel": "Cancel·lar"
```

- [ ] **Step 5: Add keys to fr.json**

```json
"color.hag": "Hauteur Culture",
"color.hag.desc": "Hauteur au-dessus du sol",
"color.canopy": "Canopée vs Couvert",
"color.canopy.desc": "Cime des arbres vs sous-bois",
"color.density": "Densité",
"color.density.desc": "Approximation structure verticale",
"uploadClassification": "Classification",
"classificationNative": "Déjà classifié (PNOA, DJI Terra, Pix4D...)",
"classificationAuto": "Non classifié — auto-classifier",
"classificationDetect": "Je ne sais pas — détecter automatiquement",
"hasRgb": "A des couleurs RGB",
"continue": "Continuer",
"cancel": "Annuler"
```

- [ ] **Step 6: Add keys to pt.json**

```json
"color.hag": "Altura da Cultura",
"color.hag.desc": "Altura acima do solo",
"color.canopy": "Copa vs Cobertura",
"color.canopy.desc": "Copa da árvore vs sub-bosque",
"color.density": "Densidade",
"color.density.desc": "Proxy de estrutura vertical",
"uploadClassification": "Classificação",
"classificationNative": "Já vem classificado (PNOA, DJI Terra, Pix4D...)",
"classificationAuto": "Não classificado — auto-classificar",
"classificationDetect": "Não sei — detetar automaticamente",
"hasRgb": "Tem cor RGB",
"continue": "Continuar",
"cancel": "Cancelar"
```

- [ ] **Step 7: Verify all 6 locales have the same key count**

```bash
for f in src/locales/*.json; do echo -n "$(basename $f): "; python3 -c "import json; print(len(json.load(open('$f'))))"; done
# Expected: all 6 output the same number (112)
```

- [ ] **Step 8: Commit**

```bash
git add src/locales/*.json
git commit -m "feat(lidar): add i18n keys for classification modes, legend, and upload modal"
```

---

## Task 10: Build, upload, and smoke test

**Files:**
- Modify: none (deploy step)

- [ ] **Step 1: Typecheck and build**

```bash
npm run typecheck && npm run build
```

Expected: 0 TypeScript errors, dist/nkz-module.js produced.

- [ ] **Step 2: Upload IIFE to MinIO (correct bucket: nekazari-frontend)**

```bash
FILE_B64=$(base64 -w0 dist/nkz-module.js)
ssh g@109.123.252.120 "sudo kubectl exec -n nekazari deploy/lidar-api -- /opt/conda/bin/python -c \"
import boto3, os, base64
from botocore.client import Config
data = base64.b64decode('\$FILE_B64')
client = boto3.client('s3', endpoint_url='http://minio-service:9000',
    aws_access_key_id=os.environ['MINIO_ACCESS_KEY'],
    aws_secret_access_key=os.environ['MINIO_SECRET_KEY'],
    config=Config(signature_version='s3v4'), region_name='us-east-1')
client.put_object(Bucket='nekazari-frontend', Key='modules/lidar/nkz-module.js', Body=data, ContentType='application/javascript')
print(f'Uploaded {len(data)} bytes')
\""
```

- [ ] **Step 3: Build and push backend Docker image**

```bash
docker build -f backend/Dockerfile -t ghcr.io/nkz-os/nkz-module-lidar/lidar-backend:latest ./backend
docker push ghcr.io/nkz-os/nkz-module-lidar/lidar-backend:latest
```

- [ ] **Step 4: Deploy**

```bash
ssh g@109.123.252.120 "
  sudo kubectl delete pod -n nekazari -l app=lidar-api
  sudo kubectl delete pod -n nekazari -l app=lidar-worker
  sudo kubectl exec -n nekazari deploy/redis -- redis-cli -a redis123 DEL rq:worker:lidar-worker-lidar-processing
"
sleep 20
ssh g@109.123.252.120 "sudo kubectl get pods -n nekazari -l module=lidar -o wide"
# Expected: both lidar-api and lidar-worker 1/1 Running
```

- [ ] **Step 5: Verify health**

```bash
curl -s https://nkz.robotika.cloud/api/lidar/health | jq
# Expected: {"status":"healthy","module":"lidar","version":"1.0.0"}
```

- [ ] **Step 6: Commit deploy tag**

```bash
git add k8s/backend-deployment.yaml
git commit -m "deploy(lidar): classification + canopy structure v1.2.0"
git push origin feat/lidar-post-audit-remediation
```

---

## Verification Checklist

After all tasks:

- [ ] PNOA download: `Classification` mode shows brown/green/gray points per LAS class
- [ ] Drone upload (classified): same behavior
- [ ] Drone upload (unclassified): auto-classify runs, points colored by class
- [ ] `HeightAboveGround` mode: gradient shows canopy structure (low=brown, treetops=red)
- [ ] `Canopy vs Cover` mode: dark green canopy, light green understory, brown ground
- [ ] `Vertical Density` mode: blue-to-red gradient by height proxy
- [ ] `RGB` mode: true color where available
- [ ] Legend bar updates when switching modes, empty for RGB
- [ ] Upload modal shows classification question with 3 radio options + RGB checkbox
- [ ] Upload respects `classification_mode` choice
- [ ] All 6 locales show translated strings (no raw keys)
