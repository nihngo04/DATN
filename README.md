# DATN - WebGIS Sat Lo Quang Tri

Ung dung hoc may trong nhan dang vung sat lo tu anh vien tham va xay dung ban do nhay cam sat lo.

Workflow demo:

```text
upload video/anh
-> anh: resize 512x512 va goi Cloud Run /predict-image
-> video: goi Cloud Run /predict-video, luu overlay_video_base64 thanh MP4
-> chon toa do mock tu data.csv voi pixel size 4.7m
-> Settings quyet dinh tao trung hay tao diem moi cach vai km
-> neu diem moi thi luu SQLite va canh bao
-> hien thi diem sat lo, thong ke, bao cao, ban do nhay cam demo
```

## Setup

Project da co venv tai `.ven` dung Python 3.13.

```powershell
cd E:\DATN
.\.ven\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Tao file `backend\.env` tu `backend\.env.example` neu muon tach cau hinh rieng.
Neu chua co `.env`, backend se fallback doc `.env.example`.

```text
PREDICT_IMAGE_URL=https://YOUR_CLOUD_RUN_URL/predict-image
PREDICT_VIDEO_URL=https://YOUR_CLOUD_RUN_URL/predict-video
PREDICT_VIDEO_TIMEOUT_SECONDS=900
PREDICT_VIDEO_MAX_FRAMES=300
PREDICT_VIDEO_FRAME_STRIDE=1
PREDICT_VIDEO_THRESHOLD=0.3
DATABASE_PATH=E:\DATN\data\webgis.sqlite3
CSV_PATH=E:\DATN\quangtri_diemsatlo.csv
CSV_NEW_PATH=E:\DATN\data\inventory_new\quangtri_landslide_new.csv
PIXEL_SIZE_M=4.7
```

Neu van de `YOUR_CLOUD_RUN_URL`, backend se tu dung mock prediction de test giao dien.

Run API:

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Run React frontend:

```powershell
cd frontend-react
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Legacy static frontend:

```text
E:\DATN\frontend\index.html
```

Tab Phan doan co cac cach test:

- Chon file moi bang file picker.
- Chon video bang file picker va bam `Predict video`.
- Chon anh/mask mau trong `data/segment`.

Boundary:

- `data/boundary/quangtri_boundary.shp`: vung nghien cuu.
- `data/boundary/huyen/huyen_boundary.gpkg`: phan huyen, dung de gan huyen cho diem moi.

LSM:

- Neu co `data/susceptibility/*.tif`, backend tao PNG preview va hien thi LSM that tren Leaflet.
- Neu muon dung GEE/Airbus, can cung cap custom XYZ tile URL/token trong tab Setting.

## Data CSV

File `data.csv` co schema:

```text
lon,lat,huyen,xa,thon,dien_tich,quy_mo,mo_ta
```

CSV khong co thoi gian. Khi seed vao SQLite, truong `observed_at` cua diem cu duoc gan
`khong_co_du_lieu`; khi phat hien diem moi, backend tu tao ngay ghi nhan.

## Thu Muc Luu Tru

```text
data/uploads/video
data/uploads/image
data/output/video
data/output/image
data/model/segmen
data/model/extratrees
data/raster/luong_mua
data/raster/do_doc
data/raster/do_cao
data/raster/huong_suon
data/susceptibility
data/reports
```

## API Chinh

```text
POST /api/workflows/detect
POST /api/settings
POST /api/rasters
POST /api/susceptibility/maps
POST /api/reports
GET  /api/points
GET  /api/stats
GET  /api/detections
GET  /api/susceptibility/maps/latest
```
