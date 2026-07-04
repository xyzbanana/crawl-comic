# MangAPI

API backend crawl truyện tranh từ các nguồn Việt Nam (NetTruyen, TruyenQQ...).
Xây dựng bằng **FastAPI + httpx + BeautifulSoup4**, deploy trên **Render.com**.

---

## Cấu trúc project

```
mangapi/
├── main.py                 # FastAPI app, routes
├── requirements.txt
├── Dockerfile
├── render.yaml
├── core/
│   ├── http.py             # HTTP client, cache, retry, anti-bot
│   ├── base_parser.py      # Abstract parser class
│   └── registry.py         # Quản lý các parser nguồn
├── parsers/
│   ├── nettruyen.py        # Parser NetTruyen
│   └── truyenqq.py         # Parser TruyenQQ
└── models/
    └── schemas.py          # Pydantic response schemas
```

---

## Chạy local

```bash
pip install -r requirements.txt
uvicorn mangapi.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

---

## API Endpoints

### System
| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/health` | Kiểm tra server |
| GET | `/sources` | Danh sách nguồn |

### Manga
| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/manga/search?q={từ khoá}&source={nguồn}&page={trang}` | Tìm kiếm |
| GET | `/manga/search/multi?q={từ khoá}` | Tìm trên tất cả nguồn |
| GET | `/manga/{source}/{slug}` | Chi tiết + danh sách chapter |
| GET | `/manga/{source}/{slug}/chapters/{chapter_id}` | URL ảnh chapter |
| GET | `/manga/{source}/listing?kind={loại}&page={trang}` | Danh sách truyện |
| GET | `/manga/{source}/genres` | Thể loại |

#### Tham số `source`
- `nettruyen` — NetTruyen (nettruyenviet.com)
- `truyenqq`  — TruyenQQ (truyenqqvip.com)

#### Tham số `kind` (listing)
- `new_update` — Mới cập nhật (mặc định)
- `top_day`    — Top ngày
- `top_week`   — Top tuần
- `top_month`  — Top tháng

### Proxy ảnh
| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/proxy/image?url={url ảnh}&referer={url trang}` | Proxy ảnh CDN |

---

## Ví dụ response

### `GET /manga/nettruyen/dao-hai-tac`
```json
{
  "source": "nettruyen",
  "slug": "dao-hai-tac",
  "title": "Đảo Hải Tặc (One Piece)",
  "cover": "https://cdn.nettruyen.../cover.jpg",
  "authors": ["Eiichiro Oda"],
  "genres": ["Action", "Adventure", "Shounen"],
  "status": "ongoing",
  "description": "...",
  "chapters": [
    { "id": "1180", "title": "Chapter 1180", "url": "...", "updated_at": "15/04/2026" }
  ]
}
```

### `GET /manga/nettruyen/dao-hai-tac/chapters/1180`
```json
{
  "source": "nettruyen",
  "manga_slug": "dao-hai-tac",
  "chapter_id": "1180",
  "pages": [
    "https://cdn.nettruyen.../page-1.jpg",
    "https://cdn.nettruyen.../page-2.jpg"
  ],
  "image_headers": {
    "Referer": "https://nettruyenviet.com/..."
  }
}
```

---

## Deploy lên Render.com

1. Push code lên GitHub
2. Vào [render.com](https://render.com) → New → Web Service → chọn repo
3. Render tự detect `render.yaml` và deploy
4. Thêm env var `ALLOWED_ORIGINS` = domain frontend của bạn

---

## Thêm nguồn mới

1. Tạo file `mangapi/parsers/ten_nguon.py`
2. Kế thừa `BaseParser`, implement 4 method bắt buộc
3. Đăng ký trong `mangapi/core/registry.py`:
```python
from ..parsers.ten_nguon import TenNguonParser
_REGISTRY["ten_nguon"] = TenNguonParser()
```

---

## Lưu ý

- **Cache**: metadata cache 5 phút, chapter cache 30 phút — giảm tải cho site nguồn
- **Rate limit**: mỗi request có delay ngẫu nhiên 0.5–1.5s tránh bị block
- **Image proxy**: ảnh CDN có hotlink protection — dùng `/proxy/image` thay vì load thẳng
- **Parser có thể vỡ**: khi site nguồn thay đổi HTML — mỗi parser độc lập, dễ sửa riêng lẻ
